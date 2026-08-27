"""平台常量与接口地址配置（基于真实站点穿透分析）。"""

BASE_URL = "https://permit.mee.gov.cn"

# 公开端核心接口
URL_HOME = BASE_URL + "/permitExt/defaults/default-index!getInformation.action"
URL_LICENSE_LIST = BASE_URL + "/perxxgkinfo/syssb/xkgg/xkgg!licenseInformation.action"
URL_LICENSE_DETAIL = BASE_URL + "/perxxgkinfo/xkgkAction!xkgk.action"
URL_LICENSE_DETAIL_ZXBG = BASE_URL + "/perxxgkinfo/xkgkAction!xkgk.action?xkgk=getxxgkContentzxbg"
URL_ZXBG_YEAR = BASE_URL + "/perxxgkinfo/syssb/wysb/hpsp/hpsp-company-sewage!getZxbgByYear.action"
URL_LICENSE_IMAGE_LIST = BASE_URL + "/perxxgkinfo/syssb/wysb/hpsp/hpsp-company-sewage!showImage.action"
URL_LICENSE_IMAGE_PAGE = BASE_URL + "/perxxgkinfo/syssb/xkgg/xkgg!downFilePng.action"
URL_LICENSE_FILE_DOWNLOAD = BASE_URL + "/perxxgkinfo/syssb/xkgg/xkgg!downloadFile.action"
URL_PRE_PUBLICITY = BASE_URL + "/perxxgkinfo/syssb/xxgk/xxgk!sqqlist.action"
URL_REGISTER_INFO = BASE_URL + "/perxxgkinfo/syssb/xkgg/xkgg!getRegisterInfo.action"

# 公告栏目
URL_ANNOUNCE_CANCEL = BASE_URL + "/perxxgkinfo/syssb/xkgg/xkgg!xkgg_zxggList.action"   # 注销
URL_ANNOUNCE_REVOKE = BASE_URL + "/perxxgkinfo/syssb/xkgg/xkgg!xkgg_cxggList.action"   # 撤销
URL_ANNOUNCE_LOST = BASE_URL + "/perxxgkinfo/syssb/xkgg/xkgg!xkgg_yssmList.action"     # 遗失
URL_NEWS_LIST = BASE_URL + "/perxxgkinfo/syssb/xkgg/xkgg!xkgg_zytzList.action"         # 重要通知
URL_RECTIFY_LIST = BASE_URL + "/perxxgkinfo/syssb/xkgg/xkgg!xxgkXqzgList.action"       # 限期整改

# 法规标准
URL_LAWS_STANDARD = BASE_URL + "/perxxgkinfo/syssb/xkgg/xkgg!lawsStandard.action"
URL_LAWS_LIST = BASE_URL + "/perxxgkinfo/syssb/xkgg/xkgg!lawsStandardList.action"
URL_NEWS_DETAIL = BASE_URL + "/perxxgkinfo/syssb/xkgg/xkgg!getNewsDetail.action"

# 排放口二维码
URL_QRCODE = BASE_URL + "/2dcode"

# 自行监测平台（详情页 iframe 对接）
URL_MONITOR_PLATFORM = "https://wryjc.mee.gov.cn/gkpt"

# AES 解密参数（详情页内联 JS 硬编码）
AES_PWD_RE = r"var pwd = '([0-9a-fA-F]+)'"
AES_WORD_RE = r"var word = '([^']+)'"

# 法规分类
LAWS_COLUMNS = {
    "Law": "法律法规",
    "XKJSGF": "许可技术规范",
    "SSHYPFBZ": "实施行业排放标准",
    "HYKXJSZN": "行业可行技术指南",
    "HYZXJCZN": "行业自行监测指南",
    "XKJGYQ": "许可监管要求",
}

# 请求行为
DEFAULT_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
REQUEST_INTERVAL = 1.0      # 秒，相邻请求最小间隔（合规限速）
RETRY_TIMES = 3             # 失败重试次数
RETRY_BACKOFF = 2.0         # 重试退避基数（秒）
TIMEOUT = 20                # 单请求超时
CACHE_TTL = 3600            # 缓存默认有效期（秒），1 小时
CACHE_DB = "permit_cache.db"
