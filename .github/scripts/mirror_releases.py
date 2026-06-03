import json
import subprocess
import sys
from pathlib import Path

def run_cmd(cmd, check=True):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"❌ Command failed: {cmd}")
        print(result.stderr)
        # 不立即退出，让脚本继续运行
        return result
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
                return json.loads(content) if content else {}
        except:
            return {}
    return {}

def save_last_synced(data):
    try:
        with open("last_synced.json", "w", encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("   💾 last_synced.json 文件已写入")
        return True
    except Exception as e:
        print(f"   ❌ 写入 last_synced.json 失败: {e}")
        return False

def main():
    config_path = Path("repo.config.json")
    if not config_path.exists():
        print("❌ Error: repo.config.json not found!")
        sys.exit(1)

    last_synced = load_last_synced()

    with open(config_path, encoding='utf-8') as f:
        repos = json.load(f)

    print("🚀 开始同步 Release (Assets 累积模式)...\n")
    updated_any = False

    for item in repos:
        owner = item["owner"]
        repo = item["repo"]
        prefix = item.get("asset_rename_prefix", repo)
        fixed_tag = repo

        print(f"{'='*90}")
        print(f"📦 处理: {owner}/{repo} → Tag: {fixed_tag}")

        release = get_latest_release(owner, repo)
        if not release:
            continue

        upstream_tag = release["tagName"]
        assets = release.get("assets", [])

        if last_synced.get(f"{owner}/{repo}") == upstream_tag:
            print(f"   ✅ 已是最新版本 ({upstream_tag})，跳过")
            continue

        print(f"   🔄 新版本: {last_synced.get(f'{owner}/{repo}') or '首次'} → {upstream_tag}")

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
            new_name = f"{prefix}-{upstream_tag}-{original_name}" if rename_assets else original_name
            print(f"   📦 {'重命名' if rename_assets else '保持原名'}: {original_name}")

            local_path = temp_dir / new_name
            run_cmd(f'curl -L -H "Accept: application/octet-stream" -H "Authorization: token $GH_TOKEN" "{download_url}" -o "{local_path}"')
            downloaded_files.append(str(local_path))

        if not downloaded_files:
            print("   ⚠️ 没有资产文件，跳过")
            continue

        files_str = " ".join(f'"{f}"' for f in downloaded_files)

        if run_cmd(f"gh release view {fixed_tag} --json tagName", check=False).returncode == 0:
            print(f"   ➕ 追加新 Assets...")
            run_cmd(f'gh release upload "{fixed_tag}" {files_str} --clobber')
        else:
            print(f"   ✨ 首次创建 Release...")
            body = f"""Mirrored from [{owner}/{repo}](https://github.com/{owner}/{repo}/releases/tag/{upstream_tag})
**上游版本**: `{upstream_tag}`"""
            run_cmd(f'gh release create "{fixed_tag}" --title "{prefix} Latest" --notes \'{body}\' {files_str}')

        print(f"   🎉 处理完成: {fixed_tag} (上游: {upstream_tag})")

        last_synced[f"{owner}/{repo}"] = upstream_tag
        updated_any = True

        run_cmd(f"rm -rf {temp_dir}", check=False)

    if updated_any:
        if save_last_synced(last_synced):
            # 自动提交并推送 last_synced.json
            print("   📤 正在提交 last_synced.json 到仓库...")
            run_cmd('git config user.name "github-actions[bot]"')
            run_cmd('git config user.email "41898282+github-actions[bot]@users.noreply.github.com"')
            run_cmd('git add last_synced.json')
            run_cmd('git commit -m "chore: update last_synced.json"')
            run_cmd('git push')
            print("   ✅ last_synced.json 已成功提交并推送")
    else:
        print("   ℹ️ 没有仓库更新，跳过保存")

    print("\n🎉 所有仓库处理完成！")

if __name__ == "__main__":
    main()
