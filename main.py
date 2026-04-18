from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from cas_parser import parse_cas_pdf
from ltv_engine import calculate_eligible_loan
from chat_engine import get_chat_response
from pydantic import BaseModel, Field


app = FastAPI(title="LAMF Python Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class HistoryTurn(BaseModel):
    role: str           # "user" | "assistant"
    content: str
 
 
class ChatRequest(BaseModel):
    message: str        = Field(..., min_length=1, max_length=1000)
    portfolio: dict     = Field(...)
    history: list[HistoryTurn] = Field(default_factory=list)
 
 
class ChatResponse(BaseModel):
    reply: str
    status: str = "ok"

@app.get("/health")
def health():
    return {"status": "ok", "service": "LAMF Python Service"}

# CAS Upload + Parse
@app.post("/parse-cas")
async def parse_cas(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files accepted")

    contents = await file.read()
    result = parse_cas_pdf(contents)

    if result["status"] == "error":
        raise HTTPException(status_code=422, detail=result["message"])

    return result

# LTV Calculation
@app.post("/calculate-ltv")
async def calculate_ltv(body: dict):
    funds = body.get("funds", [])
    if not funds:
        raise HTTPException(status_code=400, detail="No funds provided")

    try:
        ltv = calculate_eligible_loan(funds)
        return ltv
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LTV calculation failed: {str(e)}")
    

@app.post("/analyze-cas")
async def analyze_cas(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files accepted")
    
    contents = await file.read()

    parsed = parse_cas_pdf(contents)

    if parsed["status"] == "error":
        raise HTTPException(status_code=422, detail=parsed["message"])

    try:
        ltv = calculate_eligible_loan(parsed["funds"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LTV calculation failed: {str(e)}")

    return {
        "investor": parsed["investor"],
        "funds": parsed["funds"],
        "summary": parsed["summary"],
        "ltv": ltv
    }

# Chatbot
@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if not req.portfolio.get("investor"):
        raise HTTPException(status_code=400, detail="Portfolio data missing investor field")
 
    history_dicts = [t.model_dump() for t in req.history]
 
    reply = get_chat_response(
        message=req.message,
        portfolio=req.portfolio,
        history=history_dicts,
    )
 
    return ChatResponse(reply=reply)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
