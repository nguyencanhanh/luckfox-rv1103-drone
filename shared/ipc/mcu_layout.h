/*
 * Vung DDR danh rieng cho HPMCU. Dung chung cho firmware MCU, cong cu Linux va DTS.
 *
 * TRANG THAI: DE XUAT, CHUA KIEM CHUNG TREN BOARD.
 * Vung mac dinh cua SDK (0x40000, link.lds:5) nam trong kernel Linux (0x8000 - 0x78C364,
 * System.map + CONFIG_AUTO_ZRELADDR), nen khong dung duoc khi Linux va MCU chay dong thoi.
 * 0x01800000 nam ngoai moi vung da biet luc boot:
 *   SPL   0x0 - 0x28000, bss/stack toi 0x21E000     (rv1106_common.h:37-41)
 *   U-Boot 0x200000, 178 KB                          (dumpimage images/uboot.img)
 *   kernel 0x8000 (kernel_addr_r), fdt 0xC00000,
 *   boot.img nap tai 0xE00800, toi da 4 MB           (rv1106_common.h:25,79-82)
 * Phai kiem chung tren board: /proc/iomem, U-Boot bdinfo (relocaddr), doc lai sau khi nap.
 * Phai khop voi: reserved-memory trong linux/dts, mcu_region.env va defconfig cua board MCU.
 */
#ifndef MCU_LAYOUT_H
#define MCU_LAYOUT_H

#define MCU_REGION_BASE     0x01800000u
#define MCU_REGION_SIZE     0x00040000u

#define MCU_CODE_BASE       MCU_REGION_BASE
#define MCU_CODE_SIZE       0x0003C000u

/* vong dem log cua drv_pstore.c (CONFIG_PERSISTENT_RAM_ADDR/SIZE) */
#define MCU_LOG_BASE        (MCU_REGION_BASE + 0x3C000u)
#define MCU_LOG_SIZE        0x00003000u

/* struct mcu_bench_shared */
#define MCU_BENCH_BASE      (MCU_REGION_BASE + 0x3F000u)
#define MCU_BENCH_SIZE      0x00001000u

#endif
