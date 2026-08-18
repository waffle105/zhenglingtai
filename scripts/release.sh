#!/usr/bin/env bash
# 政令台 · 发布脚本（D10）
# ============================================
# 用途：打包后自动生成 SHA256SUMS，让用户能验证 zip 完整性。
# 用法：bash scripts/release.sh [version]
#   version 默认从 SKILL.md frontmatter 读取
# 产出：
#   政令台-v{version}.zip
#   政令台-v{version}.tar.gz
#   SHA256SUMS
# 注释规范：每步写"为什么"

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
BUNDLE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORK_ROOT="$(cd "${BUNDLE_ROOT}/.." && pwd)"

# 读版本号
VERSION="${1:-}"
if [ -z "$VERSION" ]; then
    VERSION=$(grep '^version:' "${BUNDLE_ROOT}/SKILL.md" | head -1 | awk '{print $2}')
fi
echo "[release] 版本: v${VERSION}"

cd "$WORK_ROOT"

# 打 zip
OUT_ZIP="政令台-v${VERSION}.zip"
OUT_TGZ="政令台-v${VERSION}.tar.gz"
rm -f "$OUT_ZIP" "$OUT_TGZ" SHA256SUMS

python3 -c "
import zipfile, tarfile
from pathlib import Path
src = Path('zhenglingtai')

# v1.0.1：打包排除运行产物与备份，发布包只含源文件
# v1.0.3 加固：补 .pytest_cache / .coverage / .git——
# v1.0.2 的 zip 里就混进了 4 个 .pytest_cache 文件（文件数核对时才发现）
EXCLUDE_SUFFIX = ('.bak', '.pyc', '.coverage')
EXCLUDE_PARTS = {'__pycache__', '.pytest_cache', '.git'}
EXCLUDE_NAMES = {'.coverage'}

def keep(f: Path) -> bool:
    if f.suffix in EXCLUDE_SUFFIX:
        return False
    if EXCLUDE_PARTS & set(f.parts):
        return False
    if f.name in EXCLUDE_NAMES:
        return False
    return True

with zipfile.ZipFile('${OUT_ZIP}', 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in sorted(src.rglob('*')):
        if not f.is_file() or not keep(f):
            continue
        arc = str(f.relative_to(src.parent)).replace('\\\\', '/')
        # v1.0.1：显式构造 ZipInfo 并强制 UTF-8 标志位（flag_bits 0x800），
        # 避免中文文件名在标准 unzip 下乱码（v1.0.0 的 zip 即踩此坑）
        info = zipfile.ZipInfo(arc)
        info.flag_bits |= 0x800
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        zf.writestr(info, f.read_bytes())
with tarfile.open('${OUT_TGZ}', 'w:gz') as tf:
    tf.add(str(src), arcname='zhenglingtai', filter=lambda t: t if keep(Path(t.name)) else None)
print('  ✔ 打包完成（UTF-8 文件名 + 排除运行产物）')
"

# 生成 SHA256SUMS
echo "[release] 生成 SHA256SUMS ..."
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$OUT_ZIP" "$OUT_TGZ" > SHA256SUMS
elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$OUT_ZIP" "$OUT_TGZ" > SHA256SUMS
else
    # v1.0.1：Windows 上 print 默认输出 CRLF，sha256sum -c 会把 \r 当文件名——
    # 强制 LF 行尾
    python3 -c "
import hashlib, sys
sys.stdout.reconfigure(newline='')
for f in ['${OUT_ZIP}', '${OUT_TGZ}']:
    h = hashlib.sha256(open(f,'rb').read()).hexdigest()
    sys.stdout.write(f'{h}  {f}\n')
" > SHA256SUMS
fi

echo "[release] 产物："
ls -lh "$OUT_ZIP" "$OUT_TGZ" SHA256SUMS
echo ""
echo "[release] 用户验证方法："
echo "  sha256sum -c SHA256SUMS          # Linux/macOS"
echo "  certutil -hashfile $OUT_ZIP SHA256  # Windows"
