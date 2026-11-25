import urllib.request
import urllib.error
import re
import time
import concurrent.futures

HOST = "https://raw.githubusercontent.com/"

# 1. 精选高可用源列表
SOURCES = [
    HOST + "Guovin/iptv-api/gd/output/result.m3u",
    HOST + "vbskycn/iptv/master/tv/iptv4.m3u",
    HOST + "mhmdxahmd/mafly/main/MAfly1/mafly.m3u",
    HOST + "mhmdxahmd/mafly/main/youtube.m3u",
    HOST + "mhmdxahmd/mafly/main/%E5%90%84TVBOX/4gtv.m3u",
    HOST + "Kimentanm/aptv/master/m3u/iptv.m3u",
    HOST + "suxuang/myIPTV/main/ipv4.m3u",
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
        "keywords": ["卫视"]
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

DIRECT_FAST_CDN = re.compile(r"(alicdn|aliyuncs|tencent|myqcloud|cdn\.dnsv1|bdydns|baidubce|miguvideo|chinamobile|10086|unicom|10010|chinatelecom|189\.cn|cctv\.com|cntv|ysten|gitv|wasu|bestv|akamaized|cloudfront|fastly)", re.I)

def normalize_channel_name(group, raw_name):
    name = raw_name.strip()
    upper = name.upper()
    
    if group == "📡 央视官方频道":
        if "欧洲" in name or "美洲" in name:
            return None
        if re.search(r"CCTV[\s\-_]*0?5\+", upper):
            return "CCTV-5+"
        m = re.search(r"CCTV[\s\-_]*0?(\d+)", upper)
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
    name, clean_info, url, score = item
    if name == "CCTV-5+":
        sort_str = "cctv-05+"
    else:
        sort_str = re.sub(r'(\d+)', lambda m: m.group(1).zfill(4), name.lower())
    return (sort_str, score)

def check_stream(item):
    group, name, clean_info, url = item
    lower_url = url.lower()
    # 只允许标准 http/https 协议，剔除纯 IPv6、flv、特殊防盗链参数及内网组播转发链接
    if not lower_url.startswith(("http://", "https://")):
        return None
    if "://[" in url or "$" in url or "|" in url or "php?" in lower_url or ".flv" in lower_url or "/udp/" in lower_url or "/rtp/" in lower_url:
        return None
    
    penalty = 0.0
    if DIRECT_FAST_CDN.search(url):
        penalty = -0.5
    elif any(k in lower_url for k in ("youtube", "googlevideo", "4gtv", "hinet", "tvb")):
        penalty = 1.5

    start = time.time()
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            # 严格要求 HTTP 200/206 真实成功响应，彻底拒绝 403/404 假链接
            if resp.status in (200, 206):
                content_type = resp.headers.get("Content-Type", "").lower()
                if "text/html" in content_type or "flv" in content_type or "json" in content_type:
                    return None
                chunk = resp.read(1024)
                if not chunk:
                    return None
                lower_chunk = chunk.lower()
                if b"<html" in lower_chunk or b"<!doctype" in lower_chunk or b"error" in lower_chunk:
                    return None
                # 必须是标准 M3U8 切片列表（包含 #EXTM3U 且含 #EXTINF 或 #EXT-X-STREAM-INF）或二进制视频流
                if b"#EXTM3U" in chunk:
                    if b"#EXTINF" not in chunk and b"#EXT-X-STREAM-INF" not in chunk:
                        return None
                latency = (time.time() - start) + penalty
                return (group, name, clean_info, url, latency)
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
                        clean_info = f'#EXTINF:-1 group-title="{target_group}",{std_name}'
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

    for group, name, clean_info, url, score in tested_items:
        if group in valid_groups:
            count = channel_counts.get((group, name), 0)
            if count < MAX_LINES_PER_CHANNEL:
                channel_counts[(group, name)] = count + 1
                valid_groups[group].append((name, clean_info, url, score))

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
