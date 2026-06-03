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
        try:
            with open(path, encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.load(f)
        except:
            print("   ⚠️ last_synced.json 读取失败，使用空记录")
            return {}
    return {}

def save_last_synced(data):
    try:
        with open("last_synced.json", "w", encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("   💾 last_synced.json 已保存")
    except Exception as e:
        print(f"   ❌ 保存 last_synced.json 失败: {e}")

def release_exists(tag):
    result = run_cmd(f"gh release view {tag} --json tagName", check=False)
    return result.returncode == 0

def main():
    config_path = Path("repo.config.json")
    if not config_path.exists():
        print("❌ Error: repo.config.json not found!")
        sys.exit(1)

    last_synced = load_last_synced()
    print(f"📋 当前同步记录: {len(last_synced)} 个仓库")

    with open(config_path, encoding='utf-8') as f:
        repos = json.load(f)

    print("🚀 开始同步 Release (Assets 累积模式)...\n")

    for item in repos:
        owner = item["owner"]
        repo = item["repo"]
        prefix = item.get("asset_rename_prefix", repo)
        fixed_tag = repo

        print(f"{'='*90}")
        print(f"📦 处理: {owner}/{repo} → Tag: {fixed_tag}")

        release = get_latest_release(owner, repo)
        if not release:
            print("   ⚠️ 无法获取 release，跳过")
            continue

        upstream_tag = release["tagName"]
        assets = release.get("assets", [])

        last_tag = last_synced.get(f"{owner}/{repo}")
        if last_tag == upstream_tag:
            print(f"   ✅ 已是最新版本 ({upstream_tag})，跳过")
            continue

        print(f"   🔄 新版本: {last_tag or '首次'} → {upstream_tag}")

        rename_assets = any(not (upstream_tag.lower().lstrip('v') in a['name'].lower() or 
                                upstream_tag.lower() in a['name'].lower()) 
                           for a in assets) if assets else False

        print(f"   🔍 自动识别: {'需要重命名' if rename_assets else '保持原名'}")

        temp_dir = Path(f"temp_{repo}")
        temp_dir.mkdir(exist_ok=True)
        downloaded_files = []

        for asset in assets:
            original_name = asset["name"]
            download_url = asset["url"]

            if rename_assets:
                new_name = f"{prefix}-{upstream_tag}-{original_name}"
            else:
                new_name = original_name

            local_path = temp_dir / new_name

            run_cmd(f'''
                curl -L \
                  -H "Accept: application/octet-stream" \
                  -H "Authorization: token $GH_TOKEN" \
                  "{download_url}" -o "{local_path}"
            ''')

            downloaded_files.append(str(local_path))

        if not downloaded_files:
            print("   ⚠️ 没有资产文件，跳过")
            continue

        files_str = " ".join(f'"{f}"' for f in downloaded_files)

        if release_exists(fixed_tag):
            print(f"   ➕ 追加 Assets 到 {fixed_tag}")
            run_cmd(f'gh release upload "{fixed_tag}" {files_str} --clobber')
        else:
            print(f"   ✨ 首次创建 Release {fixed_tag}")
            body = f"""Mirrored from [{owner}/{repo}](https://github.com/{owner}/{repo}/releases/tag/{upstream_tag})
**上游版本**: `{upstream_tag}`"""
            run_cmd(f'''
                gh release create "{fixed_tag}" \
                    --title "{prefix} Latest" \
                    --notes '{body}' \
                    {files_str}
            ''')

        print(f"   🎉 处理完成: {fixed_tag} (上游: {upstream_tag})")

        # 立即更新记录并保存
        last_synced[f"{owner}/{repo}"] = upstream_tag
        save_last_synced(last_synced)        # ← 每次都保存

        run_cmd(f"rm -rf {temp_dir}", check=False)

    print("\n🎉 所有仓库处理完成！")

if __name__ == "__main__":
    main()
