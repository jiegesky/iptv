import urllib.request
import urllib.error
import re
import time
import concurrent.futures

HOST = "https://raw.githubusercontent.com/"

# 1. 双引擎精选源（国内央视/卫视主力源 + 港台高可用官方/YouTube源）
SOURCES = [
    HOST + "best-fan/iptv-sources/main/output/result.m3u",
    HOST + "Guovin/iptv-api/gd/output/result.m3u",
    HOST + "vbskycn/iptv/master/tv/iptv4.m3u",
    HOST + "mhmdxahmd/mafly/main/MAfly1/mafly.m3u",
    HOST + "mhmdxahmd/mafly/main/youtube.m3u",
    HOST + "mhmdxahmd/mafly/main/%E5%90%84TVBOX/4gtv.m3u",
    HOST + "mytv-android/mytv-android.github.io/main/tv.m3u",
    HOST + "Kimentanm/aptv/master/m3u/iptv.m3u",
    HOST + "suxuang/myIPTV/main/ipv4.m3u",
    HOST + "YueChan/Live/main/APTV.m3u",
    HOST + "iptv-org/iptv/master/streams/hk.m3u",
    HOST + "iptv-org/iptv/master/streams/tw.m3u"
]

# 2. 自定义频道分组规则与 Emoji
group_rules = [
    {
        "group_name": "📡 央视官方频道",
        "keywords": ["CCTV"]
    },
    {
        "group_name": "🎮 杰哥咪咕直播",
        "keywords": ["咪咕直播", "Migu", "咪咕视频", "咪咕4K", "咪咕体育", "咪咕"]
    },
    {
        "group_name": "🏠 全国地方台",
        "keywords": ["卫视", "影视"]
    },
    {
        "group_name": "🏝️ 港澳台频道",
        "keywords": ["翡翠台", "明珠台", "无线", "J2", "TVB", "ViuTV", "HOY", "RTHK", "港台电视", "凤凰中文", "凤凰资讯", "凤凰香港", "凤凰", "澳视", "澳门", "有线", "Now", "纬来", "东森", "三立", "本港", "中天", "民视", "台视", "年代", "TVBS"]
    },
    {
        "group_name": "🏆 体育直播频道",
        "keywords": ["体育", "足球", "篮球", "赛事", "风云足球", "劲爆体育", "五星体育", "广东体育", "高尔夫", "英超", "NBA", "爱尔达", "博斯"]
    }
]

group_order = ["📡 央视官方频道", "🎮 杰哥咪咕直播", "🏠 全国地方台", "🏝️ 港澳台频道", "🏆 体育直播频道"]

EXCLUDE = re.compile(r"(购物|导视|测试|广播|电台|教育|少儿|动画|卡通|戏曲|轮播|解说|宣传|成人|色播|福利|中学生|老故事|怀旧|第一剧场|风云剧场|文化精品|女性时尚|兵器|世界地理|卫生健康|发现之旅)", re.I)
MAX_LINES_PER_CHANNEL = 5

def normalize_channel_name(group, raw_name):
    name = raw_name.strip()
    upper = name.upper()
    
    if group == "📡 央视官方频道":
        if "欧洲" in name or "美洲" in name:
            return None
        if re.search(r"CCTV[\s\-_]*5\+", upper):
            return "CCTV-5+"
        m = re.search(r"CCTV[\s\-_]*(\d+)", upper)
        if m:
            num = int(m.group(1))
            if 1 <= num <= 17:
                return f"CCTV-{num}"
        return None

    if group == "🏝️ 港澳台频道":
        clean = re.sub(r'[\[\(（【].*?[\]\)）】]', '', name)
        clean = re.sub(r'(高清|超清|标清|4K|HD|FHD|1080P|720P|备用|线路\d+)', '', clean, flags=re.I).strip()
        if "翡翠" in clean:
            return "TVB翡翠台"
        if "明珠" in clean:
            return "TVB明珠台"
        if "凤凰中文" in clean:
            return "凤凰卫视中文台"
        if "凤凰资讯" in clean:
            return "凤凰卫视资讯台"
        if "凤凰香港" in clean:
            return "凤凰卫视香港台"
        if "VIUTV" in clean.upper() and "96" not in clean:
            return "ViuTV"
        if ("HOY" in clean.upper() and "77" in clean) or "HOY TV" in clean.upper():
            return "HOY TV"
        return clean if clean else name

    return name

def match_group(channel_name):
    name_upper = channel_name.upper()
    for rule in group_rules:
        for kw in rule["keywords"]:
            if kw.upper() in name_upper:
                return rule["group_name"]
    return None

def natural_sort_key(item):
    name, clean_info, url, latency = item
    sort_name = name.replace("CCTV-5+", "CCTV-5.5")
    parts = [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+\.?\d*)', sort_name)]
    return (parts, latency)

def check_stream(item):
    group, name, clean_info, url = item
    if "://[" in url or "$" in url or "|" in url or "php?" in url.lower():
        return None
    start = time.time()
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            if resp.status in (200, 206, 301, 302):
                content_type = resp.headers.get("Content-Type", "").lower()
                if "text/html" in content_type:
                    return None
                chunk = resp.read(512)
                if not chunk or b"<html" in chunk.lower() or b"<!doctype" in chunk.lower():
                    return None
                if b"#EXTM3U" in chunk and b"#EXT-X-ERROR" in chunk:
                    return None
                latency = time.time() - start
                return (group, name, clean_info, url, latency)
    except urllib.error.HTTPError as e:
        if e.code == 403 and group in ("📡 央视官方频道", "🏠 全国地方台", "🎮 杰哥咪咕直播"):
            return (group, name, clean_info, url, 9.9)
    except Exception:
        pass
    return None

def main():
    candidates = []
    seen_urls = set()

    for src in SOURCES:
        try:
            req = urllib.request.Request(src, headers={'User-Agent': 'Mozilla/5.0'})
            lines = urllib.request.urlopen(req, timeout=10).read().decode('utf-8', errors='ignore').splitlines()
            line_iter = iter(lines)
            for raw_line in line_iter:
                line = raw_line.strip()
                if line.startswith("#EXTINF"):
                    url = next(line_iter, "").strip()
                    if not url.startswith("http") or url in seen_urls:
                        continue
                    _, _, raw_name = line.rpartition(",")
                    raw_name = raw_name.strip()
                    if EXCLUDE.search(raw_name):
                        continue
                    target_group = match_group(raw_name)
                    if target_group:
                        std_name = normalize_channel_name(target_group, raw_name)
                        if not std_name:
                            continue
                        seen_urls.add(url)
                        clean_info = re.sub(r'group-title="[^"]*"', f'group-title="{target_group}"', line)
                        if 'group-title=' not in clean_info:
                            clean_info = clean_info.replace("#EXTINF:-1", f'#EXTINF:-1 group-title="{target_group}"')
                        prefix, _, _ = clean_info.rpartition(",")
                        clean_info = f"{prefix},{std_name}"
                        candidates.append((target_group, std_name, clean_info, url))
                elif "," in line and "#genre#" not in line and not line.startswith("#"):
                    raw_name, _, url = line.partition(",")
                    raw_name = raw_name.strip()
                    url = url.strip()
                    if not url.startswith("http") or url in seen_urls or EXCLUDE.search(raw_name):
                        continue
                    target_group = match_group(raw_name)
                    if target_group:
                        std_name = normalize_channel_name(target_group, raw_name)
                        if not std_name:
                            continue
                        seen_urls.add(url)
                        clean_info = f'#EXTINF:-1 group-title="{target_group}",{std_name}'
                        candidates.append((target_group, std_name, clean_info, url))
        except Exception as e:
            print(f"跳过源 {src}: {e}")

    tested_items = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        for res in executor.map(check_stream, candidates):
            if res:
                tested_items.append(res)

    tested_items.sort(key=lambda x: x[-1])

    valid_groups = {g: [] for g in group_order}
    channel_counts = {}

    for group, name, clean_info, url, latency in tested_items:
        if group in valid_groups:
            norm_name = re.sub(r'[\s\-_高清超清4KHD]+', '', name.upper())
            count = channel_counts.get((group, norm_name), 0)
            if count < MAX_LINES_PER_CHANNEL:
                channel_counts[(group, norm_name)] = count + 1
                valid_groups[group].append((name, clean_info, url, latency))

    for group in group_order:
        valid_groups[group].sort(key=natural_sort_key)

    epg = "https://gh-proxy.org" + HOST + "mhmdxahmd/mafly/main/youtube.xmltv"
    with open("tv/my_live.m3u", "w", encoding="utf-8") as f:
        f.write(f'#EXTM3U x-tvg-url="{epg}"\n')
        for group in group_order:
            for name, clean_info, url, _ in valid_groups[group]:
                f.write(f"{clean_info}\n{url}\n")

    with open("tv/my_live.txt", "w", encoding="utf-8") as f:
        for group in group_order:
            if valid_groups[group]:
                f.write(f"{group},#genre#\n")
                for name, clean_info, url, _ in valid_groups[group]:
                    f.write(f"{name},{url}\n")

if __name__ == "__main__":
    main()
