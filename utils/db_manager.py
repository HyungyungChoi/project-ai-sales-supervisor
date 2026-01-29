import streamlit as st
from supabase import create_client, Client
from datetime import datetime
import json
import pandas as pd

# 1. Supabase 클라이언트 연결 (싱글톤 패턴 + 캐싱)
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase = init_supabase()

def fetch_global_avg_score():
    """전체 상담 기록의 평균 점수를 반환합니다."""
    try:
        # ai_score 컬럼만 가져와서 평균 계산 (MVP 최적화)
        res = supabase.table("coaching_logs").select("ai_score").execute()
        if not res.data:
            return 0
        
        scores = [r['ai_score'] for r in res.data]
        return sum(scores) / len(scores)
    except Exception as e:
        print(f"전체 평균 조회 실패: {e}")
        return 0

# ==========================================
# 💾 파일 업로드 (Supabase Storage)
# ==========================================
import uuid

def upload_audio_file(file_bytes, file_ext="mp3"):
    """
    Supabase Storage 'recordings' 버킷에 오디오를 업로드하고 Public URL을 반환합니다.
    """
    try:
        filename = f"{uuid.uuid4()}.{file_ext}"
        bucket = "recordings"
        
        # Upload
        supabase.storage.from_(bucket).upload(
            path=filename,
            file=file_bytes,
            file_options={"content-type": f"audio/{file_ext}"}
        )
        
        # Get Public URL
        # get_public_url returns a string directly in newer generic clients, 
        # but let's check return type. Usually it's a string url.
        public_url = supabase.storage.from_(bucket).get_public_url(filename)
        return public_url
    except Exception as e:
        # st.error might be annoying if called from non-ui context but fine here
        print(f"오디오 업로드 에러: {e}") 
        return None

        return None

def upload_reference_file(file_bytes, file_ext="pdf"):
    """
    Supabase Storage 'references' 버킷에 파일을 업로드하고 Public URL을 반환합니다.
    """
    try:
        filename = f"{uuid.uuid4()}.{file_ext}"
        bucket = "references"
        
        # Upload
        # content-type 설정: pdf, docx 등
        mime_type = "application/pdf"
        if file_ext == "docx": mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif file_ext == "txt": mime_type = "text/plain"
        
        supabase.storage.from_(bucket).upload(
            path=filename,
            file=file_bytes,
            file_options={"content-type": mime_type}
        )
        
        public_url = supabase.storage.from_(bucket).get_public_url(filename)
        return public_url
    except Exception as e:
        print(f"파일 업로드 에러: {e}") 
        return None

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

def create_profile_if_not_exists(user, is_admin=False):
    """
    첫 로그인 시 프로필 생성 (is_admin 파라미터 추가)
    """
    existing = get_user_profile(user.id)
    if not existing:
        # 가입 시 메타데이터에 저장된 권한 요청 확인
        if not is_admin and user.user_metadata:
             is_admin = user.user_metadata.get("is_admin_request", False)
             
        new_profile = {
            "id": user.id,
            "email": user.email,
            "is_admin": is_admin,       # 가입 시 선택한 값 반영
            "is_consultant": True,      # 기본적으로 상담원 권한은 가짐
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

def update_guideline_content(guideline_id, new_content):
    """가이드라인 내용을 수정합니다"""
    return supabase.table("guidelines").update({"refined_content": new_content}).eq("id", guideline_id).execute()

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



        # 2. 고객 정보 업데이트 (History Append) - customer_id가 있을 때만
        if customer_id:
            try:
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
            except Exception as e:
                print(f"고객 이력 업데이트 실패 (ID: {customer_id}): {e}")
        
        return True
    except Exception as e:
        st.error(f"저장 중 오류 발생: {e}")
        return False
        
    finally:
        # [추가] 3. 프로필 통계 업데이트 (Total Count & Avg Score)
        try:
            # 전체 로그 다시 조회해서 정확하게 계산 (MVP 방식)
            res = supabase.table("coaching_logs").select("ai_score").eq("user_id", user_id).execute()
            all_logs = res.data if res.data else []
            
            if all_logs:
                new_count = len(all_logs)
                new_avg = sum([l['ai_score'] for l in all_logs]) / new_count
                
                supabase.table("profiles").update({
                    "total_coaching_count": new_count,
                    "avg_score": round(new_avg, 1)
                }).eq("id", user_id).execute()
        except Exception as e:
            print(f"프로필 통계 업데이트 실패: {e}")
    
    
# [추가] 개발자 모드용: 권한 토글 함수
def update_user_role(user_id, is_admin):
    """
    유저의 관리자 권한을 켜거나 끕니다.
    """
    supabase.table("profiles").update({"is_admin": is_admin}).eq("id", user_id).execute()

def update_user_department(user_id, dept):
    """
    유저의 부서 정보를 업데이트합니다.
    """
    supabase.table("profiles").update({"department": dept}).eq("id", user_id).execute()

def fetch_all_profiles():
    """관리자 페이지에서 상담원 목록을 보기 위해 모든 프로필을 가져옵니다."""
    return supabase.table("profiles").select("*").order("created_at").execute().data

def fetch_consultant_stats(user_id):
    """
    상담원 대시보드용: 최근 기록과 주요 취약점을 분석합니다.
    """
    # 1. 최근 10건 로그 조회
    # Recent Logs (Recent 20)
    try:
        res = supabase.table("coaching_logs").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(20).execute()
        logs = res.data if res.data else []
    except:
        logs = []
    
    recent_avg = 0
    if logs:
        recent_avg = sum([l['ai_score'] for l in logs]) / len(logs)

    # [NEW] Category Counts (All Time)
    category_counts = {}
    try:
        # Fetch only type column for lightweight counting
        res_all = supabase.table("coaching_logs").select("consultation_type").eq("user_id", user_id).execute()
        print("DEBUG: res_all data count:", len(res_all.data) if res_all.data else 0)
        
        if res_all.data:
            df = pd.DataFrame(res_all.data)
            print("DEBUG: DF columns:", df.columns)
            if "consultation_type" in df.columns:
                category_counts = df["consultation_type"].value_counts().to_dict()
                print("DEBUG: Calculated counts:", category_counts)
    except Exception as e:
        print(f"Error fetching category counts: {e}") 
        
    return {
        "recent_logs": logs,
        "recent_avg": round(recent_avg, 1),
        "category_counts": category_counts
    }

# ==========================================
# ⚙️ 상담 유형(Category) 관리 & 통계
# ==========================================

def fetch_consultation_types(include_desc=False):
    """DB에 등록된 활성 상담 유형 목록을 가져옵니다."""
    try:
        res = supabase.table("consultation_types").select("name, description").eq("is_active", True).execute()
        if not res.data:
            return ["refund", "tech", "inquiry", "general"] # Fallback
            
        if include_desc:
            return res.data # [{'name': '...', 'description': '...'}, ...]
        else:
            return [r['name'] for r in res.data]
    except:
        return ["refund", "tech", "inquiry", "general"] # Fallback

def add_consultation_type(name, description=None):
    """새 상담 유형 추가"""
    try:
        data = {"name": name}
        if description:
            data["description"] = description
        supabase.table("consultation_types").insert(data).execute()
        return True, "성공"
    except Exception as e:
        return False, str(e)

def deactivate_consultation_type(name):
    """상담 유형 비활성화 (Soft Delete: 이름 변경 및 is_active=False)"""
    new_name = f"{name}(Unused_{datetime.now().strftime('%m%d%H%M')})"
    try:
        supabase.table("consultation_types").update({
            "name": new_name,
            "is_active": False
        }).eq("name", name).execute()
        return True
    except Exception as e:
        print(f"삭제 실패: {e}")
        return False

def fetch_kpi_trend():
    """
    관리자 대시보드 그래프용: 전체 상담 기록을 조회합니다.
    (날짜, 점수, 상담유형)
    """
    try:
        return supabase.table("coaching_logs")\
            .select("created_at, ai_score, consultation_type")\
            .order("created_at")\
            .execute().data
    except:
        return []

# ==========================================
# 📚 참고자료(Reference Materials) 관리
# ==========================================

def fetch_references(category=None):
    """
    활성화된 참고자료 목록을 조회합니다.
    category가 있으면 해당 카테고리 + 'common'(공통) 자료를 가져옵니다.
    """
    try:
        query = supabase.table("reference_materials").select("*").eq("is_active", True)
        if category:
            # category가 특정값 OR 'common' 인 것 조회
            # Supabase-py의 or_ 필터 사용
            query = query.or_(f"category.eq.{category},category.eq.common")
        
        return query.order("created_at", desc=True).execute().data
    except Exception as e:
        print(f"참고자료 조회 실패: {e}")
        return []

def add_reference(category, title, content, summary=None, file_url=None):
    """새 참고자료를 추가합니다."""
    try:
        data = {
            "category": category,
            "title": title,
            "content": content,
            "summary": summary if summary else content[:200],
            "file_url": file_url
        }
        supabase.table("reference_materials").insert(data).execute()
        return True, "저장 성공"
    except Exception as e:
        return False, str(e)

def delete_reference(ref_id):
    """참고자료 삭제 (Soft Delete)"""
    try:
        supabase.table("reference_materials").update({"is_active": False}).eq("id", ref_id).execute()
        return True
    except Exception as e:
        print(f"참고자료 삭제 실패: {e}")
        return False