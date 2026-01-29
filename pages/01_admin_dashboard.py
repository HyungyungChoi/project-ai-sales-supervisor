import streamlit as st
import pandas as pd
from utils.db_manager import (
    fetch_all_kpi_data, 
    fetch_all_guidelines, 
    add_new_guideline, 
    fetch_all_profiles,
    fetch_consultation_types,
    add_consultation_type,
    deactivate_consultation_type,
    fetch_kpi_trend,
    fetch_references,
    add_reference,
    delete_reference
)
from utils.ai_agent import refine_guideline_with_ai, generate_reference_usage_context
import altair as alt
import time

st.set_page_config(page_title="Admin Dashboard", page_icon="📊", layout="wide")

# 권한 체크
if "profile" not in st.session_state or not st.session_state.profile.get("is_admin"):
    st.error("접근 권한이 없습니다.")
    st.stop()

st.title("📊 Admin Dashboard")

# 탭 구성 (Category 관리 탭 추가)
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 성과 분석 (KPI)", "📜 가이드라인 관리", "📑 상담 유형 관리", "📚 자료실 관리", "👥 상담원 현황"])

# ----------------------------------------------------
# TAB 1: KPI Overview
# ----------------------------------------------------
with tab1:
    st.subheader("종합 성과 지표")
    
    # 데이터 로드
    raw_logs = fetch_all_kpi_data() # List of dicts
    
    if raw_logs:
        df = pd.DataFrame(raw_logs)
        df["created_at"] = pd.to_datetime(df["created_at"])
        if df["created_at"].dt.tz is None:
             df["created_at"] = df["created_at"].dt.tz_localize("UTC")
        df["created_at"] = df["created_at"].dt.tz_convert("Asia/Seoul")
        
        # 메트릭 계산
        total_sessions = len(df)
        avg_score = df["ai_score"].mean() if not df.empty else 0
        
        col1, col2, col3 = st.columns(3)
        col1.metric("총 상담 횟수", f"{total_sessions}건")
        col2.metric("전체 평균 AI 점수", f"{avg_score:.1f}점")
        
        st.divider()
        st.markdown("### 📈 전체 평균 점수 변화 추이")
        
        # 필터링
        types = ["All"] + fetch_consultation_types()
        selected_type = st.selectbox("상담 유형 필터", types)
        
        chart_df = df.copy()
        if selected_type != "All":
            chart_df = chart_df[chart_df["consultation_type"] == selected_type]
            
        if not chart_df.empty:
            # 시간순 정렬
            chart_df = chart_df.sort_values("created_at")
            chart_df["일자"] = chart_df["created_at"].dt.strftime("%Y-%m-%d")
            
            # 일별 평균 계산
            daily_avg = chart_df.groupby("일자")["ai_score"].mean().reset_index()
            
            # Altair Chart
            chart = alt.Chart(daily_avg).mark_line(point=True).encode(
                x="일자",
                y=alt.Y("ai_score", title="평균 점수", scale=alt.Scale(domain=[0, 100])),
                tooltip=["일자", "ai_score"]
            ).interactive()
            
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info(f"'{selected_type}' 유형의 데이터가 없습니다.")

    else:
        st.info("아직 누적된 상담 데이터가 없습니다.")

# ----------------------------------------------------
# TAB 2: Guideline Management
# ----------------------------------------------------
with tab2:
    st.subheader("상담 가이드라인 관리")
    
    # 카테고리 로딩 (동적)
    active_types = fetch_consultation_types()
    
    col_list, col_add = st.columns([1, 1])
    
    with col_list:
        st.markdown("#### 📋 현재 가이드라인 목록")
        guidelines = fetch_all_guidelines()
        if guidelines:
            # 카테고리별 그룹화
            df_guide = pd.DataFrame(guidelines)
            categories = df_guide["category"].unique().tolist()
            
            # 탭 생성
            cat_tabs = st.tabs([f"📂 {c}" for c in categories])
            
            for i, cat in enumerate(categories):
                with cat_tabs[i]:
                    cat_data = df_guide[df_guide["category"] == cat]
                    for _, row in cat_data.iterrows():
                        with st.expander(f"{row['raw_input'][:30]}..."):
                            st.caption(f"Raw: {row['raw_input']}")
                            st.markdown(f"**Refined:**\n{row['refined_content']}")
                            # 삭제 기능 등은 추후 추가 가능
        else:
            st.info("등록된 가이드라인이 없습니다.")

    with col_add:
        st.markdown("#### ➕ 새 가이드라인 추가 (AI Refinement)")
        
        category = st.selectbox("카테고리 선택", ["common"] + active_types)
        raw_input = st.text_area("거친 지시사항 (Raw Input)", placeholder="예: 환불 절대 해주지 마! 떼써도 안된다고 해.")
        
        if st.button("AI 정제 요청"):
            with st.spinner("AI가 예쁘게 다듬는 중..."):
                refined = refine_guideline_with_ai(category, raw_input)
                st.session_state["temp_refined"] = refined
                st.rerun()
        
        if "temp_refined" in st.session_state:
            st.success("변환 완료!")
            st.text_area("정제된 가이드 (미리보기)", value=st.session_state["temp_refined"], height=300, disabled=True)
            
            if st.button("DB에 저장"):
                add_new_guideline(category, raw_input, st.session_state["temp_refined"])
                st.success("저장되었습니다!")
                del st.session_state["temp_refined"]
                st.rerun()

# ----------------------------------------------------
# TAB 3: Category Management (NEW)
# ----------------------------------------------------
with tab3:
    st.subheader("📑 상담 유형(Category) 관리")
    st.info("가이드라인 및 상담 분류에 사용되는 카테고리를 관리합니다. 삭제 시 'Unused' 처리되어 과거 데이터는 보존됩니다.")

    active_types = fetch_consultation_types()
    
    col_c1, col_c2 = st.columns([1, 1])
    
    with col_c1:
        st.markdown("#### 현재 활성 카테고리")
        for t in active_types:
            with st.container(border=True):
                c_a, c_b = st.columns([3, 1])
                c_a.write(f"**{t}**")
                if c_b.button("삭제", key=f"del_{t}"):
                    if deactivate_consultation_type(t):
                        st.success(f"'{t}' 삭제 완료")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("삭제 실패")

    with col_c2:
        st.markdown("#### ➕ 카테고리 추가")
        new_cat = st.text_input("새 카테고리 명 (영문 권장)", placeholder="예: promotion")
        if st.button("추가하기"):
            if not new_cat:
                st.error("이름을 입력하세요.")
            elif new_cat in active_types:
                st.error("이미 존재하는 카테고리입니다.")
            else:
                success, msg = add_consultation_type(new_cat)
                if success:
                    st.success(f"'{new_cat}' 추가 완료!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"추가 실패: {msg}")

# ----------------------------------------------------
# TAB 4: Reference Management (NEW)
# ----------------------------------------------------
with tab4:
    st.subheader("📚 자료실 (참고문헌) 관리")
    st.info("코칭 시 팩트 체크를 위해 참고할 긴 규정이나 법률을 저장합니다.")
    
    active_types = fetch_consultation_types()
    col_ref_list, col_ref_add = st.columns([1.2, 1])
    
    with col_ref_list:
        st.markdown("#### 📂 참고자료 목록")
        # 필터
        f_cat = st.selectbox("카테고리 필터", ["All", "common"] + active_types)
        
        refs = fetch_references(None if f_cat == "All" else f_cat)
        
        if refs:
            for r in refs:
                with st.expander(f"[{r['category']}] {r['title']}"):
                    st.caption(f"💡 Usage Context: {r['summary']}")
                    st.text_area("본문 내용", r['content'], height=150, disabled=True, key=f"v_{r['id']}")
                    if st.button("삭제(Soft Delete)", key=f"del_ref_{r['id']}"):
                        if delete_reference(r['id']):
                            st.success("삭제됨")
                            time.sleep(1)
                            st.rerun()
        else:
            st.info("등록된 자료가 없습니다.")

    with col_ref_add:
        st.markdown("#### ➕ 새 자료 등록")
        
        with st.form("add_ref_form"):
            in_cat = st.selectbox("카테고리", ["common"] + active_types)
            in_title = st.text_input("제목", placeholder="예: 소비자 분쟁 해결 기준")
            in_content = st.text_area("본문 (전체 내용)", height=300, placeholder="법률 조항이나 규정 전문을 붙여넣으세요.")
            st.caption("ℹ️ '등록 하기'를 누르면 AI가 **'어떤 상황에서 이 자료를 써야 하는지'**를 분석해 저장합니다.")
            
            submitted = st.form_submit_button("등록 하기")
            
            if submitted:
                if not in_title or not in_content:
                    st.error("제목과 본문은 필수입니다.")
                else:
                    with st.spinner("AI가 사용 상황(Context)을 분석 중입니다..."):
                        final_summary = generate_reference_usage_context(in_content)
                    
                    suc, msg = add_reference(in_cat, in_title, in_content, final_summary)
                    if suc:
                        st.success("등록 완료! (사용 가이드 포함)")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"실패: {msg}")

# ----------------------------------------------------
# TAB 5: Consultant Status (Enhanced)
# ----------------------------------------------------
with tab5:
    st.subheader("🏆 상담원 성과 랭킹 & 코칭 현황")
    
    profiles = fetch_all_profiles()
    logs_data = fetch_all_kpi_data()
    
    if profiles and logs_data:
        # Pre-process Logs
        log_df = pd.DataFrame(logs_data)
        
        # Calculate Trend (Last 5 scores avg - Previous avg)
        # This requires sorting by date per user
        log_df["created_at"] = pd.to_datetime(log_df["created_at"])
        trend_map = {}
        
        for uid, group in log_df.groupby("user_id"):
            group = group.sort_values("created_at")
            if len(group) >= 5:
                recent = group.tail(5)["ai_score"].mean()
                total = group["ai_score"].mean()
                trend_map[uid] = recent - total # + means improving
            else:
                trend_map[uid] = 0.0

        # Merge with Profiles
        p_df = pd.DataFrame(profiles)
        
        # Add Trend Column
        p_df["growth_rate"] = p_df["id"].map(trend_map).fillna(0.0)
        
        # Display Metrics (Top 3)
        top_performers = p_df.sort_values("avg_score", ascending=False).head(3)
        
        col_m1, col_m2, col_m3 = st.columns(3)
        
        if len(top_performers) > 0:
            top1 = top_performers.iloc[0]
            col_m1.metric("🥇 1위 (Top Score)", f"{top1['email'].split('@')[0]}", f"{top1['avg_score']:.1f}점")
        if len(top_performers) > 1:
            top2 = top_performers.iloc[1]
            col_m2.metric("🥈 2위", f"{top2['email'].split('@')[0]}", f"{top2['avg_score']:.1f}점")
        if len(top_performers) > 2:
            top3 = top_performers.iloc[2]
            col_m3.metric("🥉 3위", f"{top3['email'].split('@')[0]}", f"{top3['avg_score']:.1f}점")
            
        st.divider()
        
        col_list, col_chart = st.columns([1.5, 1])
        
        with col_list:
            st.markdown("#### 📋 성세 성과표 (Growth: 최근 5건 - 전체 평균)")
            
            # Formatted Table
            display_df = p_df[["email", "department", "total_coaching_count", "avg_score", "growth_rate"]].copy()
            display_df = display_df.rename(columns={
                "email": "상담원", 
                "department": "부서", 
                "total_coaching_count": "총 상담수", 
                "avg_score": "평균 점수",
                "growth_rate": "성장세(Trend)"
            })
            # Sort by Score
            display_df = display_df.sort_values("평균 점수", ascending=False)
            
            # Using st.dataframe with column config
            st.dataframe(
                display_df,
                column_config={
                    "평균 점수": st.column_config.ProgressColumn(
                        "평균 점수",
                        format="%.1f",
                        min_value=0,
                        max_value=100,
                    ),
                    "성장세(Trend)": st.column_config.NumberColumn(
                        "성장 확인",
                        format="%.1f",
                    )
                },
                hide_index=True,
                use_container_width=True
            )
            
        with col_chart:
            st.markdown("#### 📊 점수 분포")
            
            # Simple Bar Chart
            chart = alt.Chart(p_df).mark_bar().encode(
                x=alt.X("avg_score", title="평균 점수", bin=True),
                y=alt.Y("count()", title="인원 수"),
                tooltip=["count()"]
            ).properties(height=300)
            
            st.altair_chart(chart, use_container_width=True)

            # Scatter Plot (Count vs Score)
            scatter = alt.Chart(p_df).mark_circle(size=60).encode(
                x=alt.X("total_coaching_count", title="상담 횟수"),
                y=alt.Y("avg_score", title="평균 점수", scale=alt.Scale(domain=[0, 100])),
                tooltip=["email", "avg_score", "total_coaching_count"]
            ).properties(height=200, title="숙련도(횟수) vs 점수 상관관계")
            
            st.altair_chart(scatter, use_container_width=True)

    else:
        st.info("등록된 상담원이 없거나 데이터가 부족합니다.")