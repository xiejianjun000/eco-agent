#!/usr/bin/env python3
"""
湖南执法平台 - 案卷查询脚本
加载登录session后查询案卷台账数据

用法: python3 scripts/query_cases.py [--all] [--missing]
"""
import json, pickle, requests, sys, os

BASE_URL = "http://113.246.57.20:8507/zfyth"
COOKIE_FILE = "/tmp/zfyth_cookies.pkl"
MISSING_FILE = os.environ.get("HNZFYTH_MISSING_FILE", "/tmp/zfyth_missing_cases.json")
CASE_DIR = os.path.expanduser("~/Documents/谢建军/案卷/")

def load_session():
    if not os.path.exists(COOKIE_FILE):
        print(f"❌ Cookie 文件不存在: {COOKIE_FILE}")
        print("   请先运行 scripts/login.py 登录")
        sys.exit(1)
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    with open(COOKIE_FILE, 'rb') as f:
        for k, v in pickle.load(f).items():
            session.cookies.set(k, v)
    return session

def get_all_cases(session):
    """获取全部案卷列表"""
    all_cases = []
    page = 1
    
    while True:
        query_data = {
            'page': page,
            'rows': 100,
            'serviceParam': json.dumps({
                "LASJ_START": "",
                "LASJ_END": "",
                "CJSJ_START": "",
                "CJSJ_END": "",
                "SSQX": ""
            })
        }
        r = session.post(
            f"{BASE_URL}/general/punishment/findlist",
            data=query_data
        )
        if r.status_code != 200:
            print(f"❌ 查询失败 (page={page})")
            break
        
        data = r.json()
        rows = data.get('rows', [])
        if not rows:
            break
        
        for row in rows:
            if row.get('AJLX') in ('FQLA', 'YBCF') or row.get('LAH'):
                all_cases.append(row)
        
        page += 1
    
    return all_cases

def get_existing_files():
    """获取本地已有的案卷文件"""
    existing = set()
    if os.path.exists(CASE_DIR):
        for f in os.listdir(CASE_DIR):
            if f.endswith('.pdf'):
                # Extract company name from filename
                name = f.replace('.pdf', '').replace('(1)', '').strip()
                existing.add(name)
    return existing

def find_missing(cases, existing):
    """找出缺失的案卷"""
    missing = []
    seen = set()
    for c in cases:
        name = c['DSRMC']
        # Skip duplicates
        if name in seen:
            continue
        seen.add(name)
        
        # Check if exists
        found = False
        for ex in existing:
            if name in ex or ex in name:
                found = True
                break
        
        if not found and name not in ('冷水江市', '娄底市'):
            missing.append(c)
    
    return missing

def main():
    session = load_session()
    
    print("📊 正在获取案卷列表...")
    cases = get_all_cases(session)
    print(f"   共获取 {len(cases)} 条案卷")
    
    print("📁 正在检查本地已有文件...")
    existing = get_existing_files()
    print(f"   已有 {len(existing)} 个 PDF 文件")
    
    print("🔍 正在对比缺失案卷...")
    missing = find_missing(cases, existing)
    print(f"   缺失 {len(missing)} 个案卷")
    
    # Print summary
    print("\n" + "="*60)
    print(f"📋 汇总: 平台 {len(cases)} 条 | 本地 {len(existing)} 个 | 缺失 {len(missing)} 个")
    print("="*60)
    
    # Save missing list
    with open(MISSING_FILE, 'w') as f:
        json.dump(missing, f, ensure_ascii=False, indent=2)
    print(f"\n缺失列表已保存到: {MISSING_FILE}")
    
    # Print missing cases
    print(f"\n📝 缺失案卷列表:")
    for i, c in enumerate(missing[:20], 1):
        print(f"  {i:2d}. {c['DSRMC']:　<20s} | {c['LAH']} | {c.get('LASJ', '?')}")
    if len(missing) > 20:
        print(f"  ... 还有 {len(missing)-20} 条")

if __name__ == '__main__':
    main()
