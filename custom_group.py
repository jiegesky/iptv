import urllib.request
import urllib.error
import re
import concurrent.futures

HOST = "https://githubusercontent.com"

# 1. 上游精选源列表（融合 mafly 高质量源 + 公共稳定源，兼容 .m3u 与 .txt）
SOURCES = [
    HOST + "mhmdxahmd/mafly/main/MAfly1/mafly.m3u",
    HOST + "mhmdxahmd/mafly/main/youtube.m3u",
    HOST + "mhmdxahmd/mafly/main/%E5%90%84TVBOX/4gtv.m3u",
    HOST + "mhmdxahmd/mafly/main/%E5%90%84TVBOX/1080P_20260720123224.m3u",
    HOST + "mhmdxahmd/mafly/main/%E5%90%84TVBOX/%E6%98%93%E5%8F%91_20260720104755.m3u",
    HOST + "jiegesky/iptv/master/tv/iptv4.m3u",
    HOST + "fanmingming/live/main/tv/m3u/ipv6.m3u",
    HOST + "suxuang/myIPTV/main/ipv4.m3u",
    HOST + "Guovin/iptv-api/gd/output/result.m3u",
    HOST + "YueChan/Live/main/APTV.m3u"
]

# 2. 自定义频道分组规则与 Emoji
group_rules = [
    {
        "group_name": "📡 央视官方频道",
        "keywords": ["CCTV-1", "CCTV-2", "CCTV-3", "CCTV-4", "CCTV-5", "CCTV-5+", "CCTV-6", "CCTV-7", "CCTV-8", "CCTV-9", "CCTV-10", "CCTV-11", "CCTV-12", "CCTV-13", "CCTV-14", "CCTV-15", "CCTV-16", "CCTV-17", "CCTV"]
    },
    {
        "group_name": "🎮 杰哥咪咕直播",
        "keywords": ["咪咕直播", "Migu", "咪咕视频", "咪咕4K", "咪咕体育", "咪咕"]
    },
    {
        "group_name": "🏠 全国地方台",
        "keywords": ["卫视", "综合", "新闻", "影视", "生活", "文旅", "珠江", "大湾区", "都市", "公共"]
    },
    {
        "group_name": "🏝️ 港澳台频道",
        "keywords": ["翡翠台", "明珠台", "凤凰中文", "凤凰资讯", "澳视", "TVB", "纬来", "东森", "三立", "ViuTV", "本港", "HOY", "RTHK", "中天", "民视", "台视", "年代", "TVBS"]
    },
    {
        "group_name": "🏆 体育直播频道",
        "keywords": ["体育", "足球", "篮球", "赛事", "风云足球", "劲爆体育", "五星体育", "广东体育", "高尔夫", "英超", "NBA", "爱尔达", "博斯"]
    }
]

group_order = ["📡 央视官方频道", "🎮 杰哥咪咕直播", "🏠 全国地方台", "🏝️ 港澳台频道", "🏆 体育直播频道"]

EXCLUDE = re.compile(r"(购物|导视|测试|广播|电台|教育|少儿|动画|卡通|戏曲|轮播|解说|宣传|成人|色播|福利)", re.I)
MAX_LINES_PER_CHANNEL = 5

def match_group(channel_name):
    name_upper = channel_name.upper()
    for rule in group_rules:
        for kw in rule["keywords"]:
            if kw.upper() in name_upper:
                return rule["group_name"]
    return None

def natural_sort_key(item):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', item)]

def check_stream(item):
    group, name, clean_info, url = item
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status in (200, 206, 301, 302):
                return item
    except urllib.error.HTTPError as e:
        # 放行 403/405（国内源防海外服务器探测，但在香港/内地播放器端可正常播放）
        if e.code in (403, 405):
            return item
    except Exception:
        pass
    return None

def main():
    candidates = []
    seen_urls = set()

    for src in SOURCES:
        try:
            req = urllib.request.Request(src, headers={'User-Agent': 'Mozilla/5.0'})
            lines = urllib.request.urlopen(req, timeout=15).read().decode('utf-8', errors='ignore').splitlines()
            for i in range(len(lines)):
                line = lines[i].strip()
                if line.startswith("#EXTINF"):
                    url = lines[i+1].strip() if i + 1 < len(lines) else ""
                    if not url.startswith("http") or url in seen_urls:
                        continue
                    name = line.split(",")[-1].strip()
                    if EXCLUDE.search(name):
                        continue
                    target_group = match_group(name)
                    if target_group:
                        seen_urls.add(url)
                        clean_info = re.sub(r'group-title="[^"]*"', f'group-title="{target_group}"', line)
                        if 'group-title=' not in clean_info:
                            clean_info = clean_info.replace("#EXTINF:-1", f'#EXTINF:-1 group-title="{target_group}"')
                        candidates.append((target_group, name, clean_info, url))
                elif "," in line and "#genre#" not in line and not line.startswith("#"):
                    parts = line.split(",", 1)
                    name, url = parts.strip(), parts.strip()
                    if not url.startswith("http") or url in seen_urls or EXCLUDE.search(name):
                        continue
                    target_group = match_group(name)
                    if target_group:
                        seen_urls.add(url)
                        clean_info = f'#EXTINF:-1 group-title="{target_group}",{name}'
                        candidates.append((target_group, name, clean_info, url))
        except Exception as e:
            print(f"跳过源 {src}: {e}")

    valid_groups = {g: [] for g in group_order}
    channel_counts = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        for res in executor.map(check_stream, candidates):
            if res:
                group, name, clean_info, url = res
                if group in valid_groups:
                    norm_name = re.sub(r'[\s\-_高清超清4KHD]+', '', name.upper())
                    count = channel_counts.get((group, norm_name), 0)
                    if count < MAX_LINES_PER_CHANNEL:
                        channel_counts[(group, norm_name)] = count + 1
                        valid_groups[group].append((name, clean_info, url))

    for group in group_order:
        valid_groups[group].sort(key=natural_sort_key)

    epg = HOST + "mhmdxahmd/mafly/main/youtube.xmltv"
    with open("tv/my_live.m3u", "w", encoding="utf-8") as f:
        f.write(f'#EXTM3U x-tvg-url="{epg}"\n')
        for group in group_order:
            for name, clean_info, url in valid_groups[group]:
                f.write(f"{clean_info}\n{url}\n")

    with open("tv/my_live.txt", "w", encoding="utf-8") as f:
        for group in group_order:
            if valid_groups[group]:
                f.write(f"{group},#genre#\n")
                for name, clean_info, url in valid_groups[group]:
                    f.write(f"{name},{url}\n")

if __name__ == "__main__":
    main()
