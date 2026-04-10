from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.core.config import settings

# 初始化 FastAPI 应用
app = FastAPI(
    title=settings.PROJECT_NAME,
    debug=settings.DEBUG
)

# 配置跨域中间件 (这对于前端联调至关重要)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境建议指定具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载路由，增加版本前缀
app.include_router(router, prefix="/api/v1/evaluations")

@app.get("/")
async def root():
    return {"message": "议论文评改智能体后端已就绪", "docs": "/docs"}