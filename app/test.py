from fastapi import Request

@app.middleware("http")
async def log_body(request: Request, call_next):
    if request.url.path == "/data" and request.method == "POST":
        body = await request.body()
        print("RAW REQUEST:", body.decode("utf-8"))
    return await call_next(request)
