import json
import subprocess
import sys
from pathlib import Path

def run_cmd(cmd, check=True):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"❌ Command failed: {cmd}")
        print(result.stderr)
        sys.exit(1)
    return result

def get_latest_release(owner, repo):
    cmd = f"gh release view --repo {owner}/{repo} --json tagName,assets,name,body"
    result = run_cmd(cmd, check=False)
    if result.returncode != 0:
        print(f"⚠️  Failed to get release for {owner}/{repo}")
        return None
    return json.loads(result.stdout)

def release_exists(tag):
    """检查 Release 是否已存在"""
    result = run_cmd(f"gh release view {tag} --json tagName", check=False)
    return result.returncode == 0

def load_last_synced():
    path = Path("last_synced.json")
    if path.exists():
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_last_synced(data):
    with open("last_synced.json", "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def main():
    config_path = Path("repo.config.json")
    if not config_path.exists():
        print("❌ Error: repo.config.json not found!")
        sys.exit(1)

    last_synced = load_last_synced()

    with open(config_path, encoding='utf-8') as f:
        repos = json.load(f)

    print("🚀 开始同步 Release (Assets 累积模式)...\n")

    for item in repos:
        owner = item["owner"]
        repo = item["repo"]
        prefix = item.get("asset_rename_prefix", repo)

        # 使用 repo 名称作为固定 Tag
        fixed_tag = repo

        print(f"{'='*85}")
        print(f"📦 处理仓库: {owner}/{repo} → 固定 Tag: {fixed_tag}")

        release = get_latest_release(owner, repo)
        if not release:
            continue

        upstream_tag = release["tagName"]
        assets = release.get("assets", [])

        # 检查是否有新版本
        last_tag = last_synced.get(f"{owner}/{repo}")
        if last_tag == upstream_tag:
            print(f"   ✅ 已是最新版本 ({upstream_tag})，跳过")
            continue
        else:
            print(f"   🔄 发现新版本: {last_tag or '无记录'} → {upstream_tag}")

        # 自动判断是否需要重命名
        rename_assets = any(not (upstream_tag.lower().lstrip('v') in a['name'].lower() or 
                                upstream_tag.lower() in a['name'].lower()) 
                           for a in assets) if assets else False

        print(f"   🔍 自动识别: {'情况1 - 需要重命名' if rename_assets else '情况2 - 保持原名'}")

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

            run_cmd(f'''
                curl -L \
                  -H "Accept: application/octet-stream" \
                  -H "Authorization: token $GH_TOKEN" \
                  "{download_url}" -o "{local_path}"
            ''')

            downloaded_files.append(str(local_path))

        if not downloaded_files:
            print("   ⚠️ 没有找到资产文件，跳过")
            continue

        body = f"""Mirrored from [{owner}/{repo}](https://github.com/{owner}/{repo}/releases/tag/{upstream_tag})
**上游版本**: `{upstream_tag}`

{release.get('body', 'No description provided.')}
"""

        files_str = " ".join(f'"{f}"' for f in downloaded_files)

        # ==================== 核心逻辑：累积 Assets ====================
        if release_exists(fixed_tag):
            print(f"   ➕ Release 已存在，追加新 Assets...")
            run_cmd(f'''
                gh release upload "{fixed_tag}" {files_str} --clobber
            ''')
            print(f"   ✅ 已成功追加新版本 Assets 到 {fixed_tag}")
        else:
            print(f"   ✨ 首次创建 Release...")
            run_cmd(f'''
                gh release create "{fixed_tag}" \
                    --title "{prefix} Latest" \
                    --notes '{body}' \
                    {files_str}
            ''')
            print(f"   🎉 成功创建 Release: {fixed_tag}")

        # 更新同步记录
        last_synced[f"{owner}/{repo}"] = upstream_tag
        run_cmd(f"rm -rf {temp_dir}", check=False)

    save_last_synced(last_synced)
    print("\n💾 已更新 last_synced.json")
    print("\n🎉 所有仓库处理完成！")

if __name__ == "__main__":
    main()
