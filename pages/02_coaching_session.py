import streamlit as st
import time
import pandas as pd
from utils.db_manager import (
    get_or_create_customer, 
    fetch_active_guidelines, 
    save_coaching_result,
    fetch_consultant_stats,
    upload_audio_file,
    fetch_global_avg_score,
    fetch_consultation_types,
    fetch_consultation_types,
    fetch_references,
    supabase,
    get_user_profile
)
from utils.ai_agent import analyze_topic_and_traits, generate_coaching_feedback
import altair as alt

st.set_page_config(page_title="Smart Coaching", page_icon="🎧", layout="wide")

if "profile" not in st.session_state:
    st.warning("로그인이 필요합니다.")
    st.stop()

user_id = st.session_state.profile["id"]

# Sidebar Profile & Logout
with st.sidebar:
    st.markdown(f"### 👤 {st.session_state.profile.get('email', 'User')}")
    st.caption(f"Role: {'Admin' if st.session_state.profile.get('is_admin') else 'Consultant'}")
    
    if st.button("로그아웃 (Logout)", key="sidebar_logout"):
        supabase.auth.sign_out()
        st.session_state.clear()
        st.switch_page("app.py")

st.title("🎧 Smart Coaching Session")

# ----------------------------------------------------
# TAB LAYOUT
# ----------------------------------------------------
tab_session, tab_dashboard, tab_history = st.tabs(["🎧 코칭 세션 진행", "📊 나의 대시보드", "📜 전체 이력"])

# ====================================================
# TAB 1: 코칭 세션 (Main Workflow)
# ====================================================
with tab_session:
    # ----------------------------------------------
    # 2. NEW COACHING SESSION (Existing Logic)
    # ----------------------------------------------
    if "process_step" not in st.session_state:
        st.session_state.process_step = "input" # input -> extracted -> result

    # STEP 1: 입력 (파일 업로드 or 텍스트)
    if st.session_state.process_step == "input":
        st.info("💡 녹음 파일이나 텍스트를 입력하면, AI가 고객 정보와 주제를 자동으로 추출합니다.")
        
        tab_audio, tab_text = st.tabs(["🎤 오디오 업로드 (Default)", "📝 텍스트 입력"])
        
        script_input = None
        audio_bytes = None
        
        with tab_audio:
            uploaded_file = st.file_uploader("녹음 파일 (mp3/wav/m4a)", type=["mp3", "wav", "m4a"])
            
            audio_mime = "audio/mp3" # default
            if uploaded_file:
                # 확장자 기반 MIME 타입 추론
                if uploaded_file.name.lower().endswith(".m4a"):
                     audio_mime = "audio/mp4" # Gemini handles m4a as MP4 container
                elif uploaded_file.name.lower().endswith(".wav"):
                     audio_mime = "audio/wav"
                     
                audio_bytes = uploaded_file.read()
                st.audio(uploaded_file, format=audio_mime)

        with tab_text:
            text_val = st.text_area("상담 스크립트", height=200, key="txt_in")
            if text_val: script_input = text_val

        if st.button("분석 시작 (Information Extraction)", type="primary"):
            if not (script_input or audio_bytes):
                st.error("입력된 내용이 없습니다.")
            else:
                with st.spinner("1차 분석 중: 고객 정보, 주제, 관련 자료 추출..."):
                    # [NEW] 분석에 사용할 참고자료 메타데이터 로드 (전체)
                    # 토큰 절약을 위해 필요한 필드만 추출
                    all_refs_data = fetch_references(None) # None = Fetch all
                    ref_meta_for_ai = []
                    if all_refs_data:
                        for r in all_refs_data:
                            ref_meta_for_ai.append({
                                "id": r["id"],
                                "title": r["title"],
                                "summary": r["summary"] # Usage Context
                            })
                    
                    # [NEW] 카테고리 정보 로드 (설명 포함)
                    detailed_categories = fetch_consultation_types(include_desc=True)

                    # 1차 분석 수행 (with references & categories)
                    res = analyze_topic_and_traits(
                        script=script_input, 
                        audio_data=audio_bytes,
                        mime_type=audio_mime, # 전달
                        ref_metadata=ref_meta_for_ai,
                        categories=detailed_categories
                    )
                    
                    # 세션에 저장
                    st.session_state.temp_analysis = res
                    st.session_state.temp_source = {
                        "script": script_input,
                        "audio": audio_bytes,
                        "mime_type": audio_mime # Store MIME type
                    }
                    st.session_state.process_step = "extracted"
                    st.rerun()

    # STEP 2: 추출 정보 확인 및 보정
    elif st.session_state.process_step == "extracted":
        st.success("✅ 1차 분석 완료: 고객 정보와 주제를 확인해주세요.")
        
        res = st.session_state.temp_analysis
        info = res.get("customer_info", {}) or {}
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### 👤 고객 정보 확인")
            
            # 이름/전화번호 각각 입력 (필수 체크 해제)
            c_name = st.text_input("고객명 (Name)", value=info.get("name") or "", placeholder="식별 불가시 비워두세요")
            c_phone = st.text_input("연락처 (Phone)", value=info.get("phone") or "", placeholder="이력 관리를 위한 필수값")
            
            if not c_phone:
                st.caption("⚠️ 연락처가 없으면 '방문자(Unknown)'로 기록되며 이력이 관리되지 않습니다.")
            elif not c_name:
                st.caption("ℹ️ 이름이 없으면 '고객(전화번호)'로 저장됩니다.")
                
        with col2:
            st.markdown("### 📋 상담 주제 확인")
            
            # [수정] DB에서 동적으로 불러온 카테고리 사용
            active_types = fetch_consultation_types()
            
            # [수정] AI가 추천한 Top 3 Topics 활용
            ai_topics = res.get("top_3_topics", [])
            if isinstance(ai_topics, str): ai_topics = [ai_topics] # 하위호환
            
            # 1순위 추천값을 기본값으로 설정
            default_topic = "general"
            if ai_topics and ai_topics[0] in active_types:
                default_topic = ai_topics[0]
            
            c_topic = st.selectbox("상담 유형 (1순위 추천 자동선택)", active_types, 
                                   index=active_types.index(default_topic) if default_topic in active_types else 0)
            
            # 나머지 추천 표시
            if len(ai_topics) > 1:
                others = [t for t in ai_topics if t != c_topic and t in active_types]
                if others:
                    st.caption(f"🤖 AI의 다른 제안: {', '.join(others)}")
            
            # [NEW] 관련 참고 자료 (RAG) - AI 추천 반영
            st.divider()
            st.markdown("### 📚 관련 참고 자료 Suggestions (AI Recommended)")
            
            # 1. AI가 추천한 ID 목록
            rec_ids = res.get("recommended_ref_ids", [])
            
            # 2. 전체 자료에서 추천된 것만 필터링
            all_refs = fetch_references(None) # 전체 로드
            recommended_refs = [r for r in all_refs if r['id'] in rec_ids]
            
            selected_ref_ids = []
            
            if recommended_refs:
                for r in recommended_refs:
                    # 추천된 것은 기본 체크
                    is_checked = st.checkbox(
                        f"[{r['category']}] {r['title']}", 
                        value=True, 
                        help=str(r.get('summary', '')), 
                        key=f"ref_chk_{r['id']}"
                    )
                    
                    if is_checked:
                        selected_ref_ids.append(r)
            else:
                st.info("AI가 추천한 참고자료가 없습니다.")
                
                # (옵션) 혹시 몰라 전체 리스트를 보고 싶을 수도 있으니 토글 제공?
                # User request was "아에 안보여줬으면 좋겠어" -> Hide completely.
                pass

        col_act1, col_act2 = st.columns([1, 4])
        if col_act1.button("🔙 다시 입력"):
            st.session_state.process_step = "input"
            st.rerun()
            
        if col_act2.button("FINAL 코칭 진행 ➡️", type="primary", use_container_width=True):
            # 1. 고객 조회/생성 로직 개선
            customer = None
            history = []
            
            # Case A: 전화번호가 있는 경우 -> 정식 프로필 사용
            if c_phone:
                if not c_name: c_name = f"고객-{c_phone[-4:]}" # 이름 없으면 임시이름
                customer = get_or_create_customer(c_name, c_phone)
                history = customer.get("consultation_history", [])
            
            # Case B: 전화번호가 없는 경우 -> 익명(None) 처리
            else:
                # 이름이라도 있으면 임시 객체에 담음 (저장 시 script에 병기)
                display_name = c_name if c_name else "Unknown"
                customer = {"id": None, "name": display_name, "phone": None}
                st.toast("연락처가 없어 '고객 이력'을 불러오지 못했습니다.", icon="⚠️")
            
            # 2. 2차 분석 진행
            with st.spinner("Context-Aware 코칭 생성 중... (History + Guidelines + RAG)"):
                source = st.session_state.temp_source
                guidelines = fetch_active_guidelines(c_topic)
                
                # 체크된 References만 필터링 (rerun 시 checkbox 상태 유지됨)
                final_refs = []
                # 다시 fetch하여 체크 여부 확인 (all_refs는 위에서 정의되지 않았을 수 있으므로 다시 로드)
                check_candidates = fetch_references(None) 
                if check_candidates:
                    for r in check_candidates:
                         if st.session_state.get(f"ref_chk_{r['id']}", False):
                             final_refs.append(r)
                
                final_res = generate_coaching_feedback(
                    script=source["script"],
                    audio_data=source["audio"],
                    mime_type=source.get("mime_type", "audio/mp3"), # MIME Type 전달
                    history=history,
                    guidelines=guidelines,
                    references=final_refs
                )
                
                # 결과 합성
                final_res["customer_traits"] = res.get("customer_traits")
                final_res["summary"] = res.get("summary")
                final_res["type"] = c_topic
                
                st.session_state.final_result = final_res
                st.session_state.target_customer = customer
                
                # [Auto-Save Implementation]
                # 사용자가 버튼을 안 눌러도 강제 저장
                script_to_save = final_res.get("transcript")
                top_source = st.session_state.temp_source
                if not script_to_save:
                    script_to_save = top_source["script"] if top_source["script"] else "Audio Analysis"

                # 오디오 업로드 (있다면)
                final_audio_url = None
                if top_source.get("audio"):
                    # Auto-save는 사용자 대기 시간을 최소화해야 하므로 스피너 없이 백그라운드 느낌으로 처리하거나,
                    # 짧게 처리. 여기서는 중요하므로 스피너 사용.
                    with st.spinner("💾 결과 자동 저장 중..."):
                         final_audio_url = upload_audio_file(top_source["audio"])
                
                # 비회원(Unknown) 처리
                cid = customer.get("id")
                if not cid and customer.get("name") and customer.get("name") != "Unknown":
                    script_to_save = f"[비회원 고객명: {customer['name']}]\n\n{script_to_save}"
                
                # DB 저장
                success = save_coaching_result(
                    user_id,
                    cid,
                    final_res,
                    script_to_save,
                    audio_url=final_audio_url
                )
                
                if success:
                    # 세션 프로필 통계 갱신
                    updated_profile = get_user_profile(user_id)
                    if updated_profile:
                        st.session_state.profile = updated_profile
                    st.toast("✅ 상담 결과가 자동으로 저장되었습니다!", icon="💾")
                else:
                    st.error("자동 저장 실패. 관리자에게 문의하세요.")

                st.session_state.process_step = "result"
                st.rerun()

    # STEP 3: 최종 결과 및 저장
    elif st.session_state.process_step == "result":
        final_res = st.session_state.final_result
        customer = st.session_state.target_customer
        
        st.balloons()
        st.subheader(f"🎯 코칭 결과 레포트 (고객: {customer['name']})")
        
        # 1. Score
        score = final_res.get("score", 0)
        col_score, col_metrics = st.columns([1, 2])
        
        with col_score:
            st.metric("종합 점수", f"{score}점")
            if score >= 90: st.success("Excellent!")
            elif score < 70: st.error("Improvement Needed")
            else: st.warning("Good")
            
        with col_metrics:
            m = final_res.get("metrics", {})
            c1, c2, c3 = st.columns(3)
            c1.metric("규정 준수", m.get("compliance", 0))
            c2.metric("공감/태도", m.get("empathy", 0))
            c3.metric("명확성", m.get("clarity", 0))

        # STT Transcript
        if final_res.get("transcript"):
            with st.expander("📝 대화 내용 전문 (Transcript)"):
                st.text(final_res.get("transcript"))

        # Details
        st.divider()
        st.markdown("### 💡 AI 피드백 상세")
        st.markdown(final_res.get("feedback"))
        
        st.divider()
        
        # 저장 완료 메시지 및 새 상담 시작
        st.success("✅ **[Auto-Saved]** 상담 내용과 코칭 결과가 안전하게 저장되었습니다.")
        
        if st.button("🔄 새로운 상담 시작 (New Session)", type="primary"):
            # Cleanup
            del st.session_state.process_step
            del st.session_state.temp_analysis
            del st.session_state.temp_source
            del st.session_state.final_result
            if "target_customer" in st.session_state:
                del st.session_state.target_customer
                
            time.sleep(0.5)
            st.rerun()

# Helper for KST
def format_to_kst(date_str):
    if not date_str: return ""
    try:
        dt = pd.to_datetime(date_str)
        if dt.tz is None: dt = dt.tz_localize("UTC")
        dt_kst = dt.tz_convert("Asia/Seoul")
        return dt_kst.strftime("%Y-%m-%d %H:%M")
    except:
        return date_str[:16].replace("T", " ")

# ====================================================
# TAB 2: MY DASHBOARD
# ====================================================
with tab_dashboard:
    st.subheader("📊 나의 상담 현황")
    
    stats = fetch_consultant_stats(user_id)
    logs = stats["recent_logs"]
    global_avg = fetch_global_avg_score()
    my_avg = st.session_state.profile.get('avg_score', 0)
    
    # 1. KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 상담 건수", f"{st.session_state.profile.get('total_coaching_count', 0)}건")
    c2.metric("나의 평균 점수", f"{my_avg:.1f}점")
    c3.metric("최근 10건 평균", f"{stats['recent_avg']:.1f}점")
    
    # Compare
    diff = my_avg - global_avg
    if diff >= 0:
        c4.success(f"전체 평균 대비 +{diff:.1f}점 🔼")
    else:
        c4.info(f"전체 평균 대비 {diff:.1f}점 🔽")
    
    st.divider()

    col_chart1, col_chart2 = st.columns(2)
    
    # 2. Line Chart (Score Trend)
    with col_chart1:
        st.markdown("#### 📉 점수 변화 추이 (최근 10건)")
        if logs:
            chart_data = pd.DataFrame(reversed(logs)) 
            chart_data["회차"] = range(1, len(chart_data) + 1)
            
            # KST 변환 for Tooltip
            chart_data["created_at"] = pd.to_datetime(chart_data["created_at"])
            if chart_data["created_at"].dt.tz is None:
                chart_data["created_at"] = chart_data["created_at"].dt.tz_localize("UTC")
            chart_data["created_at"] = chart_data["created_at"].dt.tz_convert("Asia/Seoul")
            chart_data["일시"] = chart_data["created_at"].dt.strftime("%Y-%m-%d %H:%M") # String for tooltip
            
            min_score = chart_data["ai_score"].min()
            y_min = max(0, min_score - 10) 
            
            chart = alt.Chart(chart_data).mark_line(point=True, strokeWidth=3).encode(
                x=alt.X("회차:O", title="상담 순서"),
                y=alt.Y("ai_score", title="점수", scale=alt.Scale(domain=[y_min, 100])),
                tooltip=["일시", "ai_score", "consultation_type"]
            ).properties(height=300)
            
            st.altair_chart(chart, use_container_width=True)
            
            # Worst Logic
            worst_log = min(logs, key=lambda x: x['ai_score'])
            if worst_log['ai_score'] < 80:
                w_date = format_to_kst(worst_log['created_at'])
                st.warning(f"⚠️ **Check**: [{w_date}] {worst_log['consultation_type']} 상담 ({worst_log['ai_score']}점)")
                
                # 버튼 클릭 시 Dialog 띄우기 (Experimental)
                @st.dialog("상담 상세 정보")
                def show_log_detail(log):
                    d_date = format_to_kst(log['created_at'])
                    st.write(f"**Date:** {d_date}")
                    st.metric("Score", f"{log['ai_score']}점")
                    st.divider()
                    st.markdown("### 💡 AI Feedback")
                    try:
                        fb = log.get('ai_feedback', '')
                        if isinstance(fb, dict): st.json(fb)
                        else: st.markdown(fb)
                    except: st.write(fb)
                    
                    st.divider()
                    st.markdown("### 📝 Transcript")
                    st.text_area("전문", log.get('original_script'), height=200)
                    if log.get('audio_url'):
                        st.audio(log['audio_url'])

                if st.button("🔍 해당 상담 상세보기"):
                    show_log_detail(worst_log)
        else:
            st.info("데이터가 부족합니다.")

    # 3. Bar Chart (Category Counts) - NEW
    with col_chart2:
        st.markdown("#### 📑 상담 유형별 건수")
        cat_counts = stats.get("category_counts", {})
        if cat_counts:
            cat_df = pd.DataFrame(list(cat_counts.items()), columns=["Type", "Count"])
            
            bar_chart = alt.Chart(cat_df).mark_bar().encode(
                x=alt.X("Type", title="상담 유형", sort="-y"),
                y=alt.Y("Count", title="상담 횟수"),
                color=alt.Color("Type", legend=None),
                tooltip=["Type", "Count"]
            ).properties(height=300)
            
            st.altair_chart(bar_chart, use_container_width=True)
        else:
            st.info("카테고리 데이터가 없습니다.")

# ====================================================
# TAB 3: HISTORY (New Tab)
# ====================================================
with tab_history:
    st.markdown("### 📋 전체 상담 이력 (최근 20건)")
    
    # DB Stats 다시 로드 or 위 stats 재사용
    # stats는 상단에서 이미 로드됨
    h_logs = stats.get("recent_logs", [])
    
    if h_logs:
        for log in h_logs:
            display_date = format_to_kst(log['created_at'])
            label = f"[{display_date}] {log['consultation_type']} (Scores: {log['ai_score']}점)"
            
            with st.expander(label):
                c_d1, c_d2 = st.columns([1, 1])
                with c_d1:
                    st.markdown("**💡 AI Feedback**")
                    try:
                        fb = log.get('ai_feedback', '')
                        if isinstance(fb, dict): st.json(fb)
                        else: st.markdown(fb) # Markdown rendering for str
                    except:
                        st.write(log.get('ai_feedback'))
                        
                with c_d2:
                    st.markdown("**📝 Transcript**")
                    st.text_area("대화 전문", log.get('original_script', ''), height=150, disabled=True, key=f"hist_{log['id']}")
                    
                    if log.get('audio_url'):
                        st.audio(log['audio_url'])
    else:
        st.info("이력이 없습니다.")