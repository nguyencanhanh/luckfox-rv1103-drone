#!/bin/bash
# run.sh — Luckfox Pico (mac dinh: Mini B + camera SC3336) tren macOS: build -> flash -> SSH + xem video.
#
#   ./run.sh                   lam tat ca: build, flash (hoi truoc), ket noi SSH + mo video
#   ./run.sh build             chi build firmware (anh ra thu muc images/)
#   ./run.sh flash             chi flash anh da build (tu vao che do nap qua ADB, khong can nut BOOT)
#   ./run.sh connect           chi ket noi board dang chay: mo video camera + SSH
#
#   ./run.sh board             xem va chon che do build (board, SD_CARD/SPI_NAND/EMMC)
#   ./run.sh board <so>        chon thang theo so thu tu trong danh sach
#   ./run.sh menuconfig kernel      chinh cau hinh kernel (driver, tinh nang)
#   ./run.sh menuconfig buildroot   them/bot phan mem trong rootfs
#   ./run.sh sdk <lenh>        chay thang ./build.sh <lenh> cua SDK (vd: sdk clean, sdk info)
#   ./run.sh shell             mo shell trong moi truong build
#   ./run.sh info              xem board dang chon, build co dang chay khong
#
#   CPUS=2 ./run.sh            build voi 2 CPU (cham hon nhung may mat hon; mac dinh 4)
#
# Chay lai bao nhieu lan cung duoc: buoc nao da xong se tu bo qua.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DL_DIR="$ROOT/dl"
IMG_DIR="$ROOT/images"
TOOLS_DIR="$ROOT/tools-rkdeveloptool"
RKDT="$TOOLS_DIR/rkdeveloptool"
BOARD_FILE="$ROOT/.board"

SDK_URL="https://codeload.github.com/LuckfoxTECH/luckfox-pico/tar.gz/refs/heads/main"
SDK_TARBALL="$DL_DIR/luckfox-pico-main.tar.gz"
# Mac dinh: Mini B = ban co SPI NAND onboard
DEFAULT_BOARD="BoardConfig_IPC/BoardConfig-SPI_NAND-Buildroot-RV1103_Luckfox_Pico_Mini-IPC.mk"

IMAGE="luckfox-build:22.04"
VOLUME="luckfox-src"
BUILDER="luckfox-builder"
CPUS="${CPUS:-4}"

BOARD_IP="172.32.0.93"
HOST_IP="172.32.0.100"
# MAC co dinh cho mang USB-ECM, de tim dung card mang phia Mac
HOST_MAC="02:4c:46:4d:42:01"
DEV_MAC="02:4c:46:4d:42:02"

STARTED_ENGINE=""

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m[x] %s\033[0m\n' "$*" >&2; exit 1; }

usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; }

current_board() {
	if [ -s "$BOARD_FILE" ]; then cat "$BOARD_FILE"; else echo "$DEFAULT_BOARD"; fi
}

# Chay lenh trong SDK, trong container Linux x86_64 (co TTY neu dang o terminal)
sdk_run() {
	local tty=-i
	[ -t 0 ] && [ -t 1 ] && tty=-it
	docker run --rm $tty --platform linux/amd64 -v "$VOLUME":/work -w /work/luckfox-pico "$IMAGE" "$@"
}

# Chay mot script bash (tu stdin) ben trong SDK
in_sdk() {
	docker run --rm -i --platform linux/amd64 -v "$VOLUME":/work -w /work/luckfox-pico "$IMAGE" bash -s
}

builder_running() {
	docker ps --filter "name=^${BUILDER}\$" --format '{{.Names}}' 2>/dev/null | grep -q .
}

not_while_building() {
	builder_running && die "Dang co build chay. Doi build xong (hoac: docker stop ${BUILDER}) roi thu lai"
	return 0
}

# ---------------------------------------------------------------- moi truong

need_docker() {
	docker info >/dev/null 2>&1 && return

	# Chi chay engine bang dong lenh, khong mo app giao dien
	if command -v orb >/dev/null; then
		say "Khoi dong OrbStack (chi engine, khong giao dien)"
		orb start >/dev/null
		STARTED_ENGINE=orb
	else
		if ! command -v colima >/dev/null; then
			command -v brew >/dev/null || die "Can Homebrew truoc: https://brew.sh"
			say "Cai Colima + Docker CLI (thuan dong lenh)"
			brew install colima docker
		fi
		say "Khoi dong Colima (co Rosetta de chay container x86_64)"
		colima start --vm-type vz --vz-rosetta --cpu "$CPUS" --memory 6 --disk 60
		STARTED_ENGINE=colima
	fi
	for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 2; done
	docker info >/dev/null 2>&1 || die "Docker engine khong khoi dong duoc"
}

# Chi tat engine neu chinh lan chay nay da bat no
cool_down() {
	case "$STARTED_ENGINE" in
		orb) say "Tat OrbStack cho may nghi"; orb stop >/dev/null 2>&1 || true ;;
		colima) say "Tat Colima cho may nghi"; colima stop >/dev/null 2>&1 || true ;;
	esac
	STARTED_ENGINE=""
}

ensure_image() {
	docker image inspect "$IMAGE" >/dev/null 2>&1 && return
	say "Tao container build Ubuntu 22.04 x86_64"
	# Dung run + commit thay cho docker build: khong can plugin buildx
	docker rm -f luckfox-image-tmp >/dev/null 2>&1 || true
	docker run --name luckfox-image-tmp --platform linux/amd64 ubuntu:22.04 bash -c '
		set -e
		export DEBIAN_FRONTEND=noninteractive
		apt-get update
		apt-get install -y --no-install-recommends \
			git ssh make gcc gcc-multilib g++-multilib module-assistant expect g++ gawk \
			texinfo libssl-dev bison flex fakeroot cmake unzip gperf autoconf \
			device-tree-compiler libncurses5-dev pkg-config bc python-is-python3 python3 \
			passwd openssl openssh-client vim file cpio rsync wget curl ca-certificates \
			patch diffutils findutils tar gzip bzip2 xz-utils lzop sudo locales \
			build-essential libc6-dev perl automake libtool subversion mtd-utils
		rm -rf /var/lib/apt/lists/*
		# Buildroot khong chay bang root
		useradd -m -u 1000 -s /bin/bash luckfox
		echo "luckfox ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers'
	docker commit \
		--change 'ENV LC_ALL=C.UTF-8 LANG=C.UTF-8' \
		--change 'USER luckfox' \
		--change 'WORKDIR /home/luckfox' \
		--change 'CMD ["/bin/bash"]' \
		luckfox-image-tmp "$IMAGE" >/dev/null
	docker rm luckfox-image-tmp >/dev/null
}

ensure_sdk() {
	if docker run --rm --platform linux/amd64 -v "$VOLUME":/work "$IMAGE" test -f /work/luckfox-pico/build.sh; then
		return
	fi
	mkdir -p "$DL_DIR"
	if [ -f "$SDK_TARBALL" ] && gzip -t "$SDK_TARBALL" 2>/dev/null; then
		say "Da co source SDK tai san: $SDK_TARBALL"
	else
		say "Tai source SDK Luckfox (~1.1 GB)"
		curl -L -C - --retry 10 --retry-all-errors --retry-delay 5 -o "$SDK_TARBALL" "$SDK_URL" || {
			warn "Khong noi tiep duoc, tai lai tu dau"
			rm -f "$SDK_TARBALL"
			curl -L --retry 10 --retry-all-errors --retry-delay 5 -o "$SDK_TARBALL" "$SDK_URL"
		}
		gzip -t "$SDK_TARBALL" || { rm -f "$SDK_TARBALL"; die "File tai ve bi hong, chay lai ./run.sh"; }
	fi
	# Giai nen trong Linux: o dia macOS khong phan biet hoa/thuong nen se lam hong source
	say "Giai nen SDK vao volume Docker (${VOLUME})"
	docker volume create "$VOLUME" >/dev/null
	docker run --rm --user 0 --platform linux/amd64 -v "$VOLUME":/work -v "$DL_DIR":/dl:ro "$IMAGE" sh -c '
		set -e; cd /work
		rm -rf luckfox-pico luckfox-pico-main
		tar xzf /dl/luckfox-pico-main.tar.gz
		mv luckfox-pico-main luckfox-pico
		chown -R 1000:1000 /work'
}

# Chon board config va bat mang USB-ECM cho macOS
prepare_sdk() {
	local board
	board="$(current_board)"
	say "Board: ${board#*/}"
	in_sdk <<EOF
set -e
[ -f "project/cfg/${board}" ] || { echo "Khong co board config: ${board}. Chon lai bang ./run.sh board"; exit 1; }
ln -rfs "project/cfg/${board}" .BoardConfig.mk

# Mac dinh board chi co mang USB kieu RNDIS, macOS khong co driver.
# Them ECM (macOS nhan san) voi MAC co dinh; ADB van giu nguyen.
F=sysdrv/tools/board/android-tools/S50usbdevice
if ! grep -q ecm.usb0 "\$F"; then
	awk '
		/^RNDIS_EN=on\$/ { print "RNDIS_EN=off"; print "ECM_EN=on"; next }
		/mkdir [\$][{]USB_FUNCTIONS_DIR[}]\/rndis[.]gs0\$/ {
			print; ind = \$0; sub(/mkdir.*/, "", ind)
			print ind "mkdir \${USB_FUNCTIONS_DIR}/ecm.usb0"
			print ind "echo ${DEV_MAC} > \${USB_FUNCTIONS_DIR}/ecm.usb0/dev_addr"
			print ind "echo ${HOST_MAC} > \${USB_FUNCTIONS_DIR}/ecm.usb0/host_addr"
			next
		}
		/test [\$]RNDIS_EN = on && syslink_function rndis[.]gs0\$/ {
			print; ind = \$0; sub(/test.*/, "", ind)
			print ind "test \$ECM_EN = on && syslink_function ecm.usb0"
			next
		}
		{ print }
	' "\$F" > "\$F.new"
	mv "\$F.new" "\$F"
	chmod +x "\$F"
fi
[ "\$(grep -c ecm.usb0 "\$F")" = 4 ] || { echo "Va S50usbdevice that bai"; exit 1; }
grep -q '^ECM_EN=on' "\$F" || { echo "Va S50usbdevice that bai"; exit 1; }

# Dat ban da va vao overlay de chac chan no nam trong rootfs cuoi cung
O=project/cfg/BoardConfig_IPC/overlay/overlay-luckfox-buildroot-init/etc/init.d
mkdir -p "\$O"
cp -f "\$F" "\$O/S50usbdevice"
EOF
}

# ---------------------------------------------------------------- build

build_fw() {
	if builder_running; then
		say "Build dang chay san, xem tiep log"
	else
		docker rm -f "$BUILDER" >/dev/null 2>&1 || true
		say "Build firmware voi ${CPUS} CPU (lan dau mat 1-3 tieng, cac lan sau nhanh hon)"
		local script
		script=$(cat <<'EOF'
set -e
cd /work/luckfox-pico
stage() { echo; echo "########## STAGE: $1 ##########"; ./build.sh "$1"; }

# Build lai U-Boot + kernel khi doi board hoac doi cau hinh kernel/U-Boot
. ./.BoardConfig.mk
K=sysdrv/source/kernel
U=sysdrv/source/uboot/u-boot
sig=$(cat .BoardConfig.mk "$K/arch/arm/configs/$RK_KERNEL_DEFCONFIG" "$K/arch/arm/boot/dts/$RK_KERNEL_DTS" \
	"$U/configs/$RK_UBOOT_DEFCONFIG" 2>/dev/null | md5sum | cut -d' ' -f1)
have_images=1
for f in uboot.img idblock.img download.bin boot.img; do [ -f "output/image/$f" ] || have_images=0; done
# Khong co chu ky thi khong biet anh cu build theo cau hinh nao: build lai U-Boot + kernel
old=$(cat output/.run_sig 2>/dev/null || true)
if [ "$sig" != "$old" ] || [ "$have_images" = 0 ]; then
	stage uboot
	stage kernel
fi
stage rootfs
stage media
stage app
stage firmware
echo "$sig" > output/.run_sig
echo "########## BUILD_OK ##########"
EOF
)
		docker run -d --name "$BUILDER" --platform linux/amd64 \
			--cpuset-cpus="0-$((CPUS - 1))" --memory=5g --memory-swap=8g \
			-v "$VOLUME":/work -w /work/luckfox-pico "$IMAGE" bash -c "$script" >/dev/null
	fi

	trap 'echo; warn "Build van chay nen. Xem tiep: ./run.sh build   |   Dung han: docker stop ${BUILDER}"; exit 130' INT
	docker logs -f --tail 30 "$BUILDER" || true
	trap - INT

	docker info >/dev/null 2>&1 || die "Docker engine bi tat giua chung. Tien do van con, chay lai ./run.sh de build tiep"

	local code
	code="$(docker wait "$BUILDER")"
	docker logs "$BUILDER" >"$ROOT/build.log" 2>&1 || true
	docker rm "$BUILDER" >/dev/null
	[ "$code" = 0 ] || die "Build loi (ma $code). Log day du: $ROOT/build.log"
}

export_images() {
	say "Chep anh firmware ra $IMG_DIR"
	mkdir -p "$IMG_DIR"
	docker run --rm --user 0 --platform linux/amd64 -v "$VOLUME":/work -v "$IMG_DIR":/out "$IMAGE" bash -c '
		set -e
		cd /work/luckfox-pico
		# Xoa anh cua lan build truoc (co the la board/che do khac)
		find /out -mindepth 1 -delete
		cp -a output/image/. /out/
		sed -n "s/^export RK_PARTITION_CMD_IN_ENV=\"\(.*\)\".*/\1/p" .BoardConfig.mk > /out/partitions.txt
		sed -n "s/^export RK_BOOT_MEDIUM=\(.*\)/\1/p" .BoardConfig.mk > /out/boot_medium.txt
		basename "$(readlink -f .BoardConfig.mk)" > /out/board.txt
		if grep -rqs ecm.usb0 --include=S50usbdevice output/; then
			echo "OK: rootfs co USB-ECM"
		else
			echo "CANH BAO: khong thay USB-ECM trong rootfs, se phai dung ADB de ket noi"
		fi'
	[ -s "$IMG_DIR/partitions.txt" ] || die "Khong doc duoc bang phan vung tu board config"
	echo "  Board: $(cat "$IMG_DIR/board.txt")   |   Khoi dong tu: $(cat "$IMG_DIR/boot_medium.txt")"
	ls -lh "$IMG_DIR"
}

do_build() {
	need_docker
	ensure_image
	ensure_sdk
	builder_running || prepare_sdk
	build_fw
	export_images
	cool_down
	say "Build xong. Anh firmware: $IMG_DIR"
}

# ---------------------------------------------------------------- chon che do / cau hinh

do_board() {
	need_docker
	ensure_image
	ensure_sdk

	local list cur n=0 line pick="${1:-}"
	list="$(docker run --rm --platform linux/amd64 -v "$VOLUME":/work -w /work/luckfox-pico/project/cfg "$IMAGE" \
		bash -c 'ls BoardConfig_*/BoardConfig-*.mk' </dev/null)"
	cur="$(current_board)"

	if [ -z "$pick" ]; then
		say "Cac che do build (* = dang chon)"
		printf '      %-4s %-9s %-10s %s\n' "So" "Luu tru" "He thong" "Board"
		while read -r line; do
			n=$((n + 1))
			local f="${line#*/BoardConfig-}"
			f="${f%.mk}"
			local medium="${f%%-*}" rest="${f#*-}"
			local system="${rest%%-*}" hw="${rest#*-}"
			local mark=" "
			[ "$line" = "$cur" ] && mark="*"
			printf '   %s  %-4s %-9s %-10s %s\n' "$mark" "$n" "$medium" "$system" "$hw"
		done <<<"$list"
		echo
		echo "  SPI_NAND = flash vao NAND tren board (Mini B)   SD_CARD = chay tu the nho (Mini A)"
		echo "  EMMC     = flash vao eMMC tren board"
		printf '\nChon so (Enter = giu nguyen): '
		read -r pick
		[ -n "$pick" ] || { cool_down; return; }
	fi

	[[ "$pick" =~ ^[0-9]+$ ]] || die "Hay nhap so thu tu"
	line="$(sed -n "${pick}p" <<<"$list")"
	[ -n "$line" ] || die "Khong co lua chon so $pick"
	echo "$line" >"$BOARD_FILE"
	say "Da chon: ${line#*/}"
	case "$line" in
		*RV1103_Luckfox_Pico_Mini*) ;;
		*) warn "Day khong phai board Mini. Build/flash chay duoc, nhung camera va mang USB chua duoc kiem tra voi board nay" ;;
	esac
	echo "  Chay ./run.sh build de build theo che do nay (neu doi board, U-Boot + kernel se tu build lai)"
	cool_down
}

do_menuconfig() {
	local target
	case "${1:-}" in
		kernel) target=kernelconfig ;;
		buildroot) target=buildrootconfig ;;
		*) die "Dung: ./run.sh menuconfig kernel   hoac   ./run.sh menuconfig buildroot" ;;
	esac
	[ -t 0 ] || die "menuconfig can chay trong terminal"
	need_docker
	ensure_image
	ensure_sdk
	not_while_building
	prepare_sdk
	sdk_run ./build.sh "$target"
	cool_down
	say "Da luu cau hinh. Chay ./run.sh build de build lai"
	[ "$1" = buildroot ] && echo "  Luu y: go bo package khoi Buildroot thi can build sach rootfs: ./run.sh sdk clean rootfs"
	return 0
}

do_sdk() {
	[ $# -gt 0 ] || die "Dung: ./run.sh sdk <lenh>   (vd: ./run.sh sdk info, ./run.sh sdk clean)"
	need_docker
	ensure_image
	ensure_sdk
	not_while_building
	prepare_sdk
	sdk_run ./build.sh "$@"
	cool_down
}

do_shell() {
	need_docker
	ensure_image
	ensure_sdk
	say "Shell trong moi truong build (go exit de thoat)"
	sdk_run bash
	cool_down
}

do_info() {
	echo "Board dang chon : $(current_board | sed 's|.*/||')"
	if [ -s "$IMG_DIR/board.txt" ]; then
		echo "Anh da build    : $(cat "$IMG_DIR/board.txt") ($(cat "$IMG_DIR/boot_medium.txt"))"
	else
		echo "Anh da build    : chua co"
	fi
	if docker info >/dev/null 2>&1; then
		if builder_running; then echo "Build           : DANG CHAY (xem: ./run.sh build)"; else echo "Build           : khong chay"; fi
	else
		echo "Docker engine   : dang tat"
	fi
}

# ---------------------------------------------------------------- flash

ensure_rkdeveloptool() {
	[ -x "$RKDT" ] && return
	command -v brew >/dev/null || die "Can Homebrew truoc: https://brew.sh"
	say "Build rkdeveloptool (cong cu flash USB cua Rockchip)"
	brew install autoconf automake libtool libusb pkg-config
	[ -d "$TOOLS_DIR" ] || git clone --depth 1 https://github.com/rockchip-linux/rkdeveloptool.git "$TOOLS_DIR"
	(
		cd "$TOOLS_DIR"
		export PATH="$(brew --prefix)/opt/libtool/libexec/gnubin:$PATH"
		autoreconf -i
		./configure
		make -j4 CXXFLAGS="-g -O2 -Wno-vla-cxx-extension -Wno-error"
	)
	[ -x "$RKDT" ] || die "Build rkdeveloptool that bai"
}

to_bytes() {
	local n="${1%[KkMmGg]}"
	case "${1#$n}" in
		K | k) echo $((n * 1024)) ;;
		M | m) echo $((n * 1024 * 1024)) ;;
		G | g) echo $((n * 1024 * 1024 * 1024)) ;;
		*) echo "$n" ;;
	esac
}

# "256K(env),256K@256K(idblock),..." -> moi dong: "<sector bat dau> <ten phan vung>"
partition_list() {
	local off=0 item size name IFS=','
	for item in $1; do
		name="${item#*(}"
		name="${name%)}"
		size="${item%%(*}"
		if [[ "$size" == *@* ]]; then
			off=$(to_bytes "${size#*@}")
			size="${size%@*}"
		fi
		echo "$((off / 512)) $name"
		[ "$size" = "-" ] || off=$((off + $(to_bytes "$size")))
	done
}

rk_mode() { "$RKDT" ld 2>/dev/null | grep -oE 'Maskrom|Loader' | head -1 || true; }

# Tu dua board dang chay Linux vao che do nap (Rockusb), khong can nut BOOT:
# "reboot loader" -> kernel dat co BOOT_BL_DOWNLOAD -> U-Boot vao Rockusb
enter_loader_auto() {
	if command -v adb >/dev/null && [ "$(adb get-state 2>/dev/null || true)" = device ]; then
		echo "  Thay board qua ADB -> adb reboot loader"
		# adbd goi thang syscall reboot kem tham so; "adb shell reboot loader" thi khong duoc
		# vi busybox trong firmware goc cua Luckfox bo qua tham so "loader"
		adb reboot loader >/dev/null 2>&1 || true
		return 0
	fi
	return 1
}

wait_rk_mode() {
	local i mode=""
	for i in $(seq 1 "$1"); do
		mode="$(rk_mode)"
		[ -n "$mode" ] && break
		sleep 1
	done
	echo "$mode"
}

# NAND / eMMC: ghi qua USB bang rkdeveloptool
flash_usb() {
	local parts="$1" sector name mode i
	ensure_rkdeveloptool
	if ! command -v adb >/dev/null && command -v brew >/dev/null; then
		say "Cai adb (de tu vao che do nap, khong can nut BOOT)"
		brew install --cask android-platform-tools || warn "Khong cai duoc adb, bo qua"
	fi

	mode="$(rk_mode)"
	if [ -z "$mode" ]; then
		say "Tu dua board vao che do nap"
		if enter_loader_auto; then
			mode="$(wait_rk_mode 30)"
		else
			echo "  Khong thay board dang chay qua ADB"
		fi
	fi

	if [ -z "$mode" ]; then
		say "Can dua board vao che do nap bang tay"
		echo "  1. Rut cap USB cua board"
		echo "  2. Giu nut BOOT tren board"
		echo "  3. Cam cap USB-C vao Mac, roi nha nut BOOT"
		echo "  (macOS co the hoi cho phep phu kien USB ket noi: chon Cho phep)"
		for i in $(seq 1 60); do
			mode="$(wait_rk_mode 5)"
			[ -n "$mode" ] && break
			# Neu ban cam board dang chay Linux thi van tu vao che do nap duoc
			enter_loader_auto >/dev/null && mode="$(wait_rk_mode 30)"
			[ -n "$mode" ] && break
		done
	fi
	[ -n "$mode" ] || die "Khong thay board o che do nap sau 5 phut"
	echo "  Thay board: $mode"

	if [ "$mode" = Maskrom ]; then
		"$RKDT" db "$IMG_DIR/download.bin"
		sleep 2
	fi

	while read -r sector name; do
		say "Ghi $name.img tai sector $sector"
		"$RKDT" wl "$sector" "$IMG_DIR/$name.img"
	done <<<"$parts"

	"$RKDT" rd
	say "Flash xong, board dang khoi dong lai"
}

# Tra ve o dia vat ly (vd disk6) chua mot duong dan
physical_disk_of() {
	local dev store
	dev="$(df "$1" | tail -1 | awk '{print $1}')"
	store="$(diskutil info "$dev" | awk -F': *' '/APFS Physical Store/{print $2}')"
	[ -n "$store" ] || store="$dev"
	diskutil info "$store" | awk -F': *' '/Part of Whole/{print $2}'
}

# SD_CARD: ghi thang tung anh vao the nho theo dia chi
flash_sd() {
	local parts="$1" disk info sector name off bs

	say "Ghi firmware vao the nho SD"
	echo "  Cam the SD (qua dau doc the) vao Mac. Danh sach o dia ngoai:"
	echo
	diskutil list external physical | sed 's/^/    /'
	printf '\nNhap ten o dia cua THE SD (vd: disk4): '
	read -r disk
	[[ "$disk" =~ ^disk[0-9]+$ ]] || die "Ten o dia khong hop le"
	info="$(diskutil info "$disk" 2>/dev/null)" || die "Khong co o dia $disk"

	# Chan cac o khong phai the nho
	[ "$disk" != "$(physical_disk_of "$ROOT")" ] || die "$disk la o dang chua project nay, khong ghi"
	[ "$disk" != "$(physical_disk_of /)" ] || die "$disk la o he thong, khong ghi"
	echo "$info" | grep -qE 'Removable Media: *Removable' || die "$disk khong phai the nho thao roi duoc (Removable Media khac Removable)"

	local size model
	size="$(echo "$info" | awk -F': *' '/Disk Size/{print $2}' | cut -d'(' -f1)"
	model="$(echo "$info" | awk -F': *' '/Media Name/{print $2}')"
	warn "TOAN BO du lieu tren $disk ($model, $size) se bi xoa"
	printf 'Go YES de tiep tuc: '
	read -r ans
	[ "$ans" = YES ] || die "Da huy"

	diskutil unmountDisk "$disk" >/dev/null
	echo "  Can mat khau Mac de ghi truc tiep vao the:"
	sudo -v
	while read -r sector name; do
		off=$((sector * 512))
		# Block lon nhat (toi da 1 MB) ma dia chi chia het, de ghi nhanh
		bs=1048576
		while [ $((off % bs)) -ne 0 ]; do bs=$((bs / 2)); done
		say "Ghi $name.img tai offset $off"
		sudo dd if="$IMG_DIR/$name.img" of="/dev/r$disk" bs="$bs" seek=$((off / bs)) conv=notrunc
	done <<<"$parts"
	sync
	diskutil eject "$disk" >/dev/null || true
	say "Ghi the xong. Rut the SD, cam vao board roi cam nguon"
	echo "  (Mini B: neu NAND con firmware thi board co the van khoi dong tu NAND)"
}

do_flash() {
	[ -f "$IMG_DIR/download.bin" ] && [ -s "$IMG_DIR/partitions.txt" ] || die "Chua co anh firmware, chay ./run.sh build truoc"

	local parts sector name medium
	parts="$(partition_list "$(cat "$IMG_DIR/partitions.txt")")"
	while read -r sector name; do
		[ -f "$IMG_DIR/$name.img" ] || die "Thieu $IMG_DIR/$name.img"
	done <<<"$parts"

	medium="$(cat "$IMG_DIR/boot_medium.txt" 2>/dev/null || echo spi_nand)"
	echo "  Anh: $(cat "$IMG_DIR/board.txt" 2>/dev/null || echo '?')   |   Khoi dong tu: $medium"
	case "$medium" in
		sd_card) flash_sd "$parts" ;;
		*) flash_usb "$parts" ;;
	esac
}

# ---------------------------------------------------------------- connect

find_ecm_if() {
	local i
	for i in $(ifconfig -l); do
		ifconfig "$i" 2>/dev/null | grep -qi "ether $HOST_MAC" && { echo "$i"; return 0; }
	done
	return 1
}

do_connect() {
	if ! command -v adb >/dev/null && command -v brew >/dev/null; then
		say "Cai adb (duong du phong neu mang USB khong len)"
		brew install --cask android-platform-tools || warn "Khong cai duoc adb, bo qua"
	fi

	say "Cho board khoi dong (toi da 2 phut)"
	local ifname="" via="" i
	for i in $(seq 1 120); do
		if ifname="$(find_ecm_if)"; then via=ecm; break; fi
		# Cho ECM 45s truoc khi chuyen sang ADB
		if [ "$i" -gt 45 ] && command -v adb >/dev/null && [ "$(adb get-state 2>/dev/null || true)" = device ]; then
			via=adb; break
		fi
		sleep 1
	done

	local host port rtsp
	case "$via" in
		ecm)
			echo "  Mang USB: $ifname"
			if ! ifconfig "$ifname" | grep -q "inet $HOST_IP "; then
				echo "  Gan IP $HOST_IP cho $ifname (can mat khau Mac cua ban):"
				sudo ifconfig "$ifname" inet "$HOST_IP" netmask 255.255.255.0 alias
			fi
			for i in $(seq 1 60); do nc -z -G 1 "$BOARD_IP" 22 2>/dev/null && break; sleep 1; done
			nc -z -G 1 "$BOARD_IP" 22 2>/dev/null || die "Co mang USB nhung khong vao duoc SSH tai $BOARD_IP"
			host="$BOARD_IP"; port=22; rtsp="rtsp://$BOARD_IP/live/0"
			;;
		adb)
			warn "Khong thay mang USB-ECM, dung ADB chuyen tiep cong"
			adb forward tcp:2222 tcp:22 >/dev/null
			adb forward tcp:8554 tcp:554 >/dev/null
			host=127.0.0.1; port=2222; rtsp="rtsp://127.0.0.1:8554/live/0"
			;;
		*)
			die "Khong thay board. Kiem tra cap USB-C (phai la cap co truyen du lieu) roi chay: ./run.sh connect"
			;;
	esac

	say "Video camera: $rtsp"
	if command -v ffplay >/dev/null; then
		sleep 3 # doi rkipc khoi dong xong
		ffplay -hide_banner -loglevel error -rtsp_transport tcp -fflags nobuffer -flags low_delay \
			-window_title "Luckfox camera" "$rtsp" >/dev/null 2>&1 &
		echo "  Da mo cua so video (ffplay)"
	elif [ -d /Applications/VLC.app ]; then
		open -a VLC "$rtsp"
	else
		echo "  Mo link tren bang VLC, hoac cai ffplay: brew install ffmpeg"
	fi

	say "SSH vao board: user root, mat khau luckfox"
	exec ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p "$port" "root@$host"
}

# ---------------------------------------------------------------- main

cmd="${1:-all}"
[ $# -gt 0 ] && shift
case "$cmd" in
	build) do_build ;;
	flash) do_flash ;;
	connect) do_connect ;;
	board) do_board "${1:-}" ;;
	menuconfig) do_menuconfig "${1:-}" ;;
	sdk) do_sdk "$@" ;;
	shell) do_shell ;;
	info) do_info ;;
	all)
		do_build
		printf '\nFlash vao board ngay bay gio? [Y/n] '
		read -r ans
		case "$ans" in n | N) exit 0 ;; esac
		do_flash
		do_connect
		;;
	-h | --help | help) usage ;;
	*) usage; exit 1 ;;
esac
