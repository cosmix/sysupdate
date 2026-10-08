# Pyapp Cpu Variant

> x86_64 binary pins v1 Python; PyApp's v3 default exits silently without AVX2

## Embedded Python CPU level

PyApp 0.22 embeds the x86_64_v3 python-build-standalone build when PYAPP_DISTRIBUTION_VARIANT is unset (pyapp build.rs, selected_variant), which dies with SIGILL on CPUs or VMs without AVX2 (Proxmox default CPU types kvm64 and x86-64-v2-AES). PyApp's check_setup_status then deletes the install dir, prints the empty captured output, and exits 1: the symptom is 'Unpacking distribution' followed by a silent exit, even for --version. The x86_64 job in .github/workflows/release.yml and build-binary.sh (on x86_64 hosts) set PYAPP_DISTRIBUTION_VARIANT=v1. Never set it for aarch64: those distributions have no variant and the build finds no match. Check an unpacked Python's level with: python3 -c "import sysconfig; print(sysconfig.get_config_var('CFLAGS'))" (look for -march).
