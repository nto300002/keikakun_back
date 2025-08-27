from slowapi import Limiter
from slowapi.util import get_remote_address

# アプリケーション全体で共有するLimiterインスタンス
limiter = Limiter(key_func=get_remote_address)
