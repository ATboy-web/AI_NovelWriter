"""
后端公共包 - ai-service 与 novel-service 共享的代码

P2-3: 两个后端服务此前各自维护一份逐字相同的 middleware(auth/logging/rate_limiter),
现抽取到本包，服务通过 app/middleware/*.py 中的薄转发层引用，改一处即两处生效。
"""
