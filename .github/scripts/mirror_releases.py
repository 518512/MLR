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

def load_last_synced():
    path = Path("last_synced.json")
    if path.exists():
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_last_synced(data):
    with open("last_synced.json", "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def should_rename_assets(assets, tag_name):
    if not assets:
        return False
    tag_clean = tag_name.lower().lstrip('v')
    for asset in assets:
        name_lower = asset['name'].lower()
        if tag_clean in name_lower or tag_name.lower() in name_lower:
            return False
    return True

def main():
    config_path = Path("repo.config.json")
    if not config_path.exists():
        print("❌ Error: repo.config.json not found!")
        sys.exit(1)

    last_synced = load_last_synced()

    with open(config_path, encoding='utf-8') as f:
        repos = json.load(f)

    print("🚀 开始同步 Release...\n")
    updated = False

    for item in repos:
        owner = item["owner"]
        repo = item["repo"]
        prefix = item.get("asset_rename_prefix", repo)

        print(f"{'='*75}")
        print(f"📦 处理仓库: {owner}/{repo}")

        release = get_latest_release(owner, repo)
        if not release:
            continue

        upstream_tag = release["tagName"]
        assets = release.get("assets", [])

        # ==================== 新增：检查是否有新版本 ====================
        last_tag = last_synced.get(f"{owner}/{repo}")
        if last_tag == upstream_tag:
            print(f"   ✅ 已是最新版本 ({upstream_tag})，跳过")
            continue
        else:
            print(f"   🔄 发现新版本: {last_tag or '无记录'} → {upstream_tag}")

        # ============================================================

        rename_assets = should_rename_assets(assets, upstream_tag)

        print(f"   🔍 自动识别: {'情况1 - 需要重命名' if rename_assets else '情况2 - 保持原名'}")

        our_tag = f"{prefix}-{upstream_tag}" if rename_assets else upstream_tag

        # 检查本仓库是否已存在该 tag
        result = run_cmd(f"gh release view {our_tag} --json tagName", check=False)
        if result.returncode == 0:
            print(f"   ✅ Tag {our_tag} 已存在，跳过")
            # 即使已存在，也更新记录（防止下次重复判断）
            last_synced[f"{owner}/{repo}"] = upstream_tag
            continue

        print(f"   📥 开始下载并创建新 Release...")

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

{release.get('body', 'No description provided.')}
"""

        files_str = " ".join(f'"{f}"' for f in downloaded_files)

        run_cmd(f'''
            gh release create "{our_tag}" \
                --title "{prefix} {upstream_tag}" \
                --notes '{body}' \
                {files_str}
        ''')

        print(f"   🎉 成功创建 Release: {our_tag}")

        # 更新记录
        last_synced[f"{owner}/{repo}"] = upstream_tag
        updated = True

        run_cmd(f"rm -rf {temp_dir}", check=False)

    # 保存同步记录
    if updated:
        save_last_synced(last_synced)
        print("\n💾 已更新 last_synced.json 记录")
    
    print("\n🎉 所有仓库处理完成！")

if __name__ == "__main__":
    main()
