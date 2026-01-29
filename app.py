import streamlit as st
import time
from utils.db_manager import supabase, create_profile_if_not_exists

# 1. 페이지 설정
st.set_page_config(
    page_title="Project PASS",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 2. 세션 상태 초기화
if "user" not in st.session_state:
    st.session_state.user = None
if "profile" not in st.session_state:
    st.session_state.profile = None

# ==========================================
# 🔐 인증 로직
# ==========================================

def login_with_email(email, password):
    try:
        # 로그인 시도
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
        st.session_state.user = res.user
        
        # 프로필 조회 및 세션 저장
        profile = create_profile_if_not_exists(res.user)
        st.session_state.profile = profile
        
        st.success("로그인 성공!")
        time.sleep(0.5)
        st.rerun() # 화면 새로고침해서 라우팅 로직 실행
            
    except Exception as e:
        st.error(f"로그인 실패: {e}")

def sign_up_with_email(email, password, role_selection):
    try:
        is_admin = (role_selection == "관리자 (Admin)")
        
        # 메타데이터에 권한 요청 정보 저장 (이메일 인증 후 로그인 시 프로필 생성에 사용)
        options = {
            "data": {
                "is_admin_request": is_admin
            }
        }
        res = supabase.auth.sign_up({"email": email, "password": password, "options": options})
        
        if res.user:
            st.success("✅ 가입 신청이 완료되었습니다!")
            st.info("📩 입력하신 이메일로 인증 링크가 발송되었습니다. 메일함 확인 후 인증을 완료해주시면 로그인이 가능합니다.")
            # 자동 로그인 시도 제거 (이메일 미인증 상태이므로)
    except Exception as e:
        err_msg = str(e)
        if "23503" in err_msg or "violates foreign key constraint" in err_msg:
             st.error("가입 실패: 이미 가입된 이메일이거나, 유효하지 않은 요청입니다. (로그인을 시도해보세요)")
        elif "User already registered" in err_msg:
             st.error("가입 실패: 이미 가입된 이메일입니다.")
        else:
            st.error(f"가입 실패 (상세): {e}")

def logout():
    supabase.auth.sign_out()
    st.session_state.user = None
    st.session_state.profile = None
    st.rerun()

# ==========================================
# 🚦 라우팅 및 UI (핵심 로직 변경)
# ==========================================

st.title("🤖 Project PASS")

# [상황 A] 비로그인 상태 -> 로그인 창 표시
if not st.session_state.user:
    st.markdown("### AI Sales Supervisor System")
    tab1, tab2 = st.tabs(["🔑 로그인", "✨ 회원가입"])
    
    with tab1:
        email = st.text_input("이메일", placeholder="admin@pass.com", key="login_email")
        password = st.text_input("비밀번호", type="password", key="login_pw")
        if st.button("로그인 시작", type="primary", use_container_width=True):
            login_with_email(email, password)

    with tab2:
        new_email = st.text_input("이메일", key="signup_email")
        new_password = st.text_input("비밀번호", type="password", key="signup_pw")
        role_selection = st.radio("가입 유형", ["상담원 (Consultant)", "관리자 (Admin)"], horizontal=True)
        if st.button("회원가입", use_container_width=True):
            sign_up_with_email(new_email, new_password, role_selection)

# [상황 B] 로그인 상태 -> 권한별 화면 분기
else:
    profile = st.session_state.profile
    
    # 1. 관리자 권한이 있는 경우 -> "허브(Hub)" 화면 표시 (선택권 부여)
    if profile.get("is_admin"):
        st.subheader(f"반갑습니다, 관리자 {profile['email']}님! 👮‍♂️")
        st.info("관리자는 업무를 선택하여 이동할 수 있습니다.")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📊 관리/통계")
            st.write("상담원들의 KPI를 분석하고\n가이드라인을 관리합니다.")
            if st.button("관리자 대시보드 입장 ➡️", use_container_width=True):
                st.switch_page("pages/01_admin_dashboard.py")
        
        with col2:
            st.markdown("### 🎧 코칭/상담")
            st.write("직접 상담을 진행하거나\n코칭 시스템을 테스트합니다.")
            if st.button("코칭 세션 입장 ➡️", use_container_width=True):
                st.switch_page("pages/02_coaching_session.py")
        
        st.divider()
        if st.button("로그아웃"):
            logout()

    # 2. 일반 상담원인 경우 -> "즉시 이동 (Fast Track)"
    else:
        # 화면 깜빡임 없이 바로 보내버림
        st.switch_page("pages/02_coaching_session.py")