import json
import subprocess
import sys
from pathlib import Path

def run_cmd(cmd, check=True):
    """执行 shell 命令"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"❌ Command failed: {cmd}")
        print(result.stderr)
        sys.exit(1)
    return result

def get_latest_release(owner, repo):
    """获取上游仓库最新 Release"""
    cmd = f"gh release view --repo {owner}/{repo} --json tagName,assets,name,body"
    result = run_cmd(cmd, check=False)
    if result.returncode != 0:
        print(f"⚠️  Failed to get release for {owner}/{repo}")
        return None
    return json.loads(result.stdout)

def tag_exists(tag):
    """检查当前仓库是否已存在该 tag"""
    result = run_cmd(f"git tag -l '{tag}'", check=False)
    return bool(result.stdout.strip())

def should_rename_assets(assets, tag_name):
    """自动判断是否需要重命名资产"""
    if not assets:
        return False
    
    tag_clean = tag_name.lower().lstrip('v')
    for asset in assets:
        name_lower = asset['name'].lower()
        if tag_clean in name_lower or tag_name.lower() in name_lower:
            return False  # 包含 tag → 情况2：保持原名
    return True  # 不包含 tag → 情况1：需要重命名

def main():
    config_path = Path("repo.config.json")
    if not config_path.exists():
        print("❌ Error: repo.config.json not found!")
        sys.exit(1)

    with open(config_path, encoding='utf-8') as f:
        repos = json.load(f)

    print("🚀 开始同步 Release...\n")

    for item in repos:
        owner = item["owner"]
        repo = item["repo"]
        # 自动生成 prefix（可手动覆盖）
        prefix = item.get("asset_rename_prefix", repo)

        print(f"{'='*75}")
        print(f"📦 处理仓库: {owner}/{repo}  (prefix: {prefix})")

        release = get_latest_release(owner, repo)
        if not release:
            continue

        upstream_tag = release["tagName"]
        assets = release.get("assets", [])

        # 自动识别类型
        rename_assets = should_rename_assets(assets, upstream_tag)
        print(f"   🔍 自动识别: {'情况1 - 需要重命名' if rename_assets else '情况2 - 保持原名'}")

        # 决定本仓库使用的 Tag
        our_tag = f"{prefix}-{upstream_tag}" if rename_assets else upstream_tag

        if tag_exists(our_tag):
            print(f"   ✅ Tag {our_tag} 已存在，跳过")
            continue

        print(f"   🔄 发现新版本: {upstream_tag} → 创建 Tag: {our_tag}")

        # 创建临时目录
        temp_dir = Path(f"temp_{repo}")
        temp_dir.mkdir(exist_ok=True)
        downloaded_files = []

        for asset in assets:
            original_name = asset["name"]
            download_url = asset["url"]

            if rename_assets:
                new_name = f"{prefix}-{upstream_tag}-{original_name}"
                print(f"   📦 重命名: {original_name} → {new_name}")
            else:
                new_name = original_name
                print(f"   📦 保持原名: {original_name}")

            local_path = temp_dir / new_name

            # 下载文件
            run_cmd(f'''
                curl -L \
                  -H "Accept: application/octet-stream" \
                  -H "Authorization: token $GH_TOKEN" \
                  "{download_url}" -o "{local_path}"
            ''')

            downloaded_files.append(str(local_path))

        if not downloaded_files:
            print("   ⚠️ 没有找到任何资产文件，跳过")
            continue

        # 准备 Release 描述
        body = f"""Mirrored from [{owner}/{repo}](https://github.com/{owner}/{repo}/releases/tag/{upstream_tag})

{release.get('body', 'No description provided.')}
"""

        files_str = " ".join(f'"{f}"' for f in downloaded_files)

        # 创建 Release 并上传文件
        run_cmd(f'''
            gh release create "{our_tag}" \
                --title "{prefix} {upstream_tag}" \
                --notes '{body}' \
                {files_str}
        ''')

        print(f"   🎉 成功创建 Release: {our_tag}")

        # 清理临时目录
        run_cmd(f"rm -rf {temp_dir}", check=False)

    print("\n🎉 所有仓库同步处理完成！")

if __name__ == "__main__":
    main()
