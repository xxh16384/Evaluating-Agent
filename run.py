import uvicorn

if __name__ == "__main__":
    # 启动服务器
    # reload=True 会在代码修改时自动重启（仅限开发模式）
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=True
    )