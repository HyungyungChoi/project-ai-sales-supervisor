import streamlit as st
from supabase import create_client, Client
from datetime import datetime
import json

# 1. Supabase 클라이언트 연결 (싱글톤 패턴 + 캐싱)
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase = init_supabase()

# ==========================================
# 👤 사용자 인증 및 프로필 관리 (Auth & Profiles)
# ==========================================

def get_user_profile(user_id):
    """
    로그인한 유저의 권한(is_admin, is_consultant) 및 정보를 가져옵니다.
    """
    try:
        response = supabase.table("profiles").select("*").eq("id", user_id).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        st.error(f"프로필 조회 실패: {e}")
        return None

def create_profile_if_not_exists(user):
    """
    첫 로그인 시 프로필이 없으면 기본값(Consultant)으로 생성합니다.
    """
    existing = get_user_profile(user.id)
    if not existing:
        new_profile = {
            "id": user.id,
            "email": user.email,
            "is_admin": False,       # 기본값
            "is_consultant": True,   # 기본값
            "total_coaching_count": 0,
            "avg_score": 0.0
        }
        supabase.table("profiles").insert(new_profile).execute()
        return new_profile
    return existing

# ==========================================
# 📊 관리자 대시보드용 (Admin Dashboard)
# ==========================================

def fetch_all_kpi_data():
    """
    상담원 랭킹, 전체 평균 점수 등을 계산하기 위해 로그 데이터를 가져옵니다.
    (MVP에서는 DB에서 연산보다 데이터를 가져와서 Pandas로 처리하는게 빠릅니다)
    """
    # 점수와 날짜, 상담원 ID만 가져옴 (데이터 절약)
    return supabase.table("coaching_logs").select(
        "ai_score, created_at, user_id, consultation_type, metrics"
    ).execute().data

def fetch_all_guidelines():
    """현재 활성화된 모든 가이드라인 조회"""
    return supabase.table("guidelines").select("*").order("category").execute().data

def add_new_guideline(category, raw_input, refined_content):
    """관리자가 입력한 새 가이드라인 추가"""
    data = {
        "category": category,
        "raw_input": raw_input,
        "refined_content": refined_content,
        "is_active": True
    }
    return supabase.table("guidelines").insert(data).execute()

# ==========================================
# 🎧 상담 코칭 및 고객 관리 (Coaching & CRM)
# ==========================================

def get_or_create_customer(name, phone, initial_trait=None):
    """
    이름/전화번호로 고객을 찾고, 없으면 새로 만듭니다.
    (AI가 1차 추론한 정보를 바탕으로 실행)
    """
    # 1. 조회
    res = supabase.table("customers").select("*").eq("phone", phone).execute()
    
    if res.data:
        return res.data[0] # 기존 고객 반환
    else:
        # 2. 신규 생성
        new_customer = {
            "name": name,
            "phone": phone,
            "consultation_history": [], # 빈 리스트로 시작
            "last_consultation_date": datetime.now().isoformat()
        }
        # 초기 특이사항이 있다면 히스토리에 넣기 애매하므로 일단 생성만
        created = supabase.table("customers").insert(new_customer).execute()
        return created.data[0]

def fetch_active_guidelines(category):
    """
    특정 상담 카테고리(예: 'refund')에 맞는 가이드라인만 RAG용으로 조회
    """
    # 공통(common) 가이드 + 해당 카테고리 가이드 합치기
    return supabase.table("guidelines").select("refined_content").or_(
        f"category.eq.common,category.eq.{category}"
    ).eq("is_active", True).execute().data

def save_coaching_result(user_id, customer_id, analysis_result, original_script, audio_url=None):
    """
    [핵심] 코칭 결과를 저장하고, 고객 정보(History)를 업데이트합니다.
    (수정사항: audio_url 인자 추가 및 DB 저장 반영)
    """
    try:
        # 1. 코칭 로그 저장
        log_data = {
            "user_id": user_id,
            "customer_id": customer_id,
            "consultation_type": analysis_result.get("type", "general"),
            "original_script": original_script,
            "audio_url": audio_url,  # [수정] 스키마에 맞춰 추가됨
            "ai_score": analysis_result.get("score", 0),
            "metrics": analysis_result.get("metrics", {}),
            "ai_feedback": analysis_result.get("feedback", ""),
        }
        supabase.table("coaching_logs").insert(log_data).execute()

        # 2. 고객 정보 업데이트 (History Append)
        # 기존 고객 정보 가져오기
        cust = supabase.table("customers").select("consultation_history").eq("id", customer_id).execute().data[0]
        history = cust["consultation_history"] if cust["consultation_history"] else []
        
        # 새 기록 추가
        new_record = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "type": analysis_result.get("type"),
            "summary": analysis_result.get("summary", "상담 내용 없음"),
            "extracted_traits": analysis_result.get("customer_traits", "")
        }
        history.append(new_record)
        
        # DB 업데이트
        supabase.table("customers").update({
            "consultation_history": history,
            "last_consultation_date": datetime.now().isoformat()
        }).eq("id", customer_id).execute()
        
        return True
    except Exception as e:
        st.error(f"저장 중 오류 발생: {e}")
        return False