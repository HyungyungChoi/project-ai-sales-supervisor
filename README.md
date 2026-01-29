# 🤖 AI Sales Supervisor (AI 세일즈 코칭 슈퍼바이저)

> **"주니어 상담원도 1년차 에이스처럼."**
> Google Gemini 2.0의 멀티모달 기능과 RAG(검색 증강 생성) 기술을 활용한 실시간 세일즈 코칭 시스템입니다.

---

## 📌 Project Overview
**AI Sales Supervisor**는 상담원의 통화 내용(Audio/Text)을 실시간으로 분석하여, **최적의 답변**과 **행동 지침**을 코칭해주는 시스템입니다.  
관리자(Admin)는 대시보드를 통해 상담원들의 성과를 모니터링하고, 가이드라인과 참고자료를 손쉽게 관리할 수 있습니다.

### 핵심 목표
1.  **실시간 코칭**: 상담 도중 놓치기 쉬운 필수 규정이나 팩트 체크를 AI가 대신 수행.
2.  **데이터 기반 성장**: 상담원의 숙련도와 점수 변화를 시각화하여 객관적인 피드백 제공.
3.  **관리 효율화**: 가이드라인 수정 및 전파 과정을 자동화하여 관리 리소스 절감.

---

## ✨ Key Features

### 1. 🎧 AI 코칭 세션 (Coaching Session)
- **멀티모달 분석**: 텍스트 스크립트뿐만 아니라 **음성 파일(MP3)**을 직접 업로드하여 분석 가능.
- **실시간 피드백**: 상담 내용의 분위기(감정), 주제, 핵심 이슈를 파악하고 **점수(Score)**와 **피드백** 제공.
- **RAG 기반 팩트 체크**: 업로드된 법률/규정(PDF, Docx)을 근거로 상담원이 잘못 안내한 내용을 교정.

### 2. 📊 관리자 대시보드 (Admin Dashboard)
- **상담원 현황판**: 상담원 랭킹, 성장세(Trend) 지표, 숙련도 vs 점수 상관관계 차트 제공.
- **가이드라인 관리**: 관리자가 거칠게 입력한 지시사항을 AI가 "상담원용 표준 스크립트"로 자동 정제(Refinement).
- **자료실(Knowledge Base)**: PDF/Word 파일을 업로드하면 AI가 "언제 사용해야 하는지" 사용 상황(Context)을 자동 분석하여 DB에 Tagging.

### 3. 📈 성과 분석 (Analytics)
- **KPI 모니터링**: 전체 상담 횟수, 평균 점수 추이, 카테고리별 성과 분석.
- **Warning System**: 최근 성과가 저조하거나 실수가 잦은 상담원 자동 식별 및 알림.

---

## 🛠️ Tech Stack

- **Frontend**: [Streamlit](https://streamlit.io/) (Python 기반 웹 프레임워크)
- **AI Model**: **Google Gemini 2.0 Flash** (Thinking Mode, Multimodal, High-speed)
- **Database**: [Supabase](https://supabase.com/) (PostgreSQL + Vector Storage)
- **Language**: Python 3.9+
- **Key Libraries**: `google-genai`, `altair` (Visualization), `pypdf/python-docx` (File Parsing)

---

## 🚀 Getting Started

### 1. Installation
프로젝트를 클론하고 필수 라이브러리를 설치합니다.
```bash
git clone [repository url]
cd project-ai-sales-supervisor
pip install -r requirements.txt
```

### 2. Configuration (`secrets.toml`)
`.streamlit/secrets.toml` 파일을 생성하고 API 키를 설정해야 합니다.
```toml
[google]
api_key = "YOUR_GEMINI_API_KEY"

[supabase]
url = "YOUR_SUPABASE_URL"
key = "YOUR_SUPABASE_ANON_KEY"
```

### 3. Run Application
```bash
streamlit run app.py
```

---

## 📂 Project Structure

```
project-ai-sales-supervisor/
├── app.py                  # 메인 진입점 (로그인 및 라우팅)
├── pages/
│   ├── 01_admin_dashboard.py    # 관리자 대시보드 (통계, 관리)
│   └── 02_coaching_session.py   # 상담원 코칭 페이지 (분석 UI)
├── utils/
│   ├── ai_agent.py         # Gemini API 연동 및 프롬프트 관리
│   ├── db_manager.py       # Supabase DB CRUD 함수
│   └── text_extractor.py   # PDF/Word 텍스트 추출 유틸
└── requirements.txt        # 의존성 목록
```

---

## 📝 License
This project is for demonstration purposes.
