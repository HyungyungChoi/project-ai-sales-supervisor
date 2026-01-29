import streamlit as st
import pandas as pd
from utils.db_manager import (
    fetch_all_kpi_data, 
    fetch_all_guidelines, 
    add_new_guideline, 
    update_guideline_content,
    fetch_all_profiles,
    fetch_consultation_types,
    add_consultation_type,
    deactivate_consultation_type,
    fetch_kpi_trend,
    fetch_references,
    add_reference,
    delete_reference,
    update_user_department,
    upload_reference_file
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

# 탭 구성 (순서 변경: 상담원 현황을 1순위로)
tab_consultants, tab_kpi, tab_guide, tab_types, tab_refs = st.tabs([
    "👥 상담원 현황", 
    "📈 성과 분석 (KPI)", 
    "📜 가이드라인 관리", 
    "📑 상담 유형 관리", 
    "📚 자료실 관리"
])

# ----------------------------------------------------
# TAB 2: KPI Overview (Moved to Second)
# ----------------------------------------------------
with tab_kpi:
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

        # [NEW] 숙련도 vs 점수 상관관계 분석 (Scatter Plot)
        st.divider()
        st.markdown("### 💠 숙련도(횟수) vs 점수 상관관계")
        
        # Consultant Data Needed (Fetch profiles or aggregate from raw_logs)
        # We need per-user aggregation: {user_id: {count: N, avg: S, name: ...}}
        # We can use fetch_all_profiles combined with raw_logs or just aggregate raw_logs if names are not critical, 
        # but for tooltips we want names.
        
        profiles_data = fetch_all_profiles()
        if profiles_data:
            scatter_df = pd.DataFrame(profiles_data)
            # Ensure columns exist
            if "total_coaching_count" in scatter_df.columns and "avg_score" in scatter_df.columns:
                 # Altair Scatter
                 scatter_chart = alt.Chart(scatter_df).mark_circle(size=100).encode(
                     x=alt.X("total_coaching_count", title="상담 횟수 (숙련도)"),
                     y=alt.Y("avg_score", title="평균 점수", scale=alt.Scale(domain=[0, 100])),
                     color=alt.Color("department", title="부서", legend=alt.Legend(orient="bottom")),
                     tooltip=["email", "department", "total_coaching_count", "avg_score"]
                 ).interactive().properties(
                     height=400
                 )
                 st.altair_chart(scatter_chart, use_container_width=True)
            else:
                st.info("상담원 데이터가 부족하여 그래프를 그릴 수 없습니다.")
        else:
            st.info("상담원 프로필 데이터가 없습니다.")

    else:
        st.info("아직 누적된 상담 데이터가 없습니다.")

# ----------------------------------------------------
# TAB 1: Consultant Status (Ranking & Growth)
# ----------------------------------------------------
with tab_consultants:
    st.subheader("🏆 상담원 성과 랭킹 & 코칭 현황")
    
    profiles = fetch_all_profiles()
    logs_data = fetch_all_kpi_data()
    
    if profiles and logs_data:
        # Pre-process Logs
        log_df = pd.DataFrame(logs_data)
        
        # Calculate Trend
        log_df["created_at"] = pd.to_datetime(log_df["created_at"])
        trend_map = {}
        for uid, group in log_df.groupby("user_id"):
            group = group.sort_values("created_at")
            if len(group) >= 5:
                recent = group.tail(5)["ai_score"].mean()
                total = group["ai_score"].mean()
                trend_map[uid] = recent - total
            else:
                trend_map[uid] = 0.0
                
        # Merge with Profiles
        p_df = pd.DataFrame(profiles)
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
            display_df = p_df[["email", "department", "total_coaching_count", "avg_score", "growth_rate"]].copy()
            display_df = display_df.rename(columns={
                "email": "상담원", "department": "부서", "total_coaching_count": "총 상담수", 
                "avg_score": "평균 점수", "growth_rate": "성장세(Trend)"
            }).sort_values("평균 점수", ascending=False)
            
            st.info("💡 '부서' 컬럼을 더블 클릭하여 수정할 수 있습니다.")
            
            edited_df = st.data_editor(
                display_df,
                column_config={
                    "평균 점수": st.column_config.ProgressColumn("평균 점수", format="%.1f", min_value=0, max_value=100),
                    "성장세(Trend)": st.column_config.NumberColumn("성장 확인", format="%.1f"),
                    "부서": st.column_config.SelectboxColumn("부서 (Edit)", options=["Sales", "CS", "Tech Support", "Retention", "General"], required=True)
                },
                disabled=["평균 점수", "성장세(Trend)", "상담원", "총 상담수"],
                hide_index=True,
                use_container_width=True,
                key="dept_editor_main"
            )
            
            if not display_df.equals(edited_df):
                diff_rows = edited_df[display_df["부서"] != edited_df["부서"]]
                if not diff_rows.empty:
                    if st.button("부서 정보 변경 사항 저장 (Save Changes)"):
                         with st.spinner("저장 중..."):
                             for idx, row in diff_rows.iterrows():
                                 target_email = row["상담원"]
                                 target_id = p_df[p_df["email"] == target_email].iloc[0]["id"]
                                 update_user_department(target_id, row["부서"])
                             st.success("✅ 부서 정보가 업데이트되었습니다!")
                             time.sleep(1)
                             st.rerun()

        with col_chart:
            st.markdown("#### 📊 점수 분포")
            chart = alt.Chart(p_df).mark_bar().encode(
                x=alt.X("avg_score", title="평균 점수", bin=True),
                y=alt.Y("count()", title="인원 수"),
                tooltip=["count()"]
            ).properties(height=300)
            st.altair_chart(chart, use_container_width=True)

    else:
        st.info("데이터가 부족합니다.")

# ----------------------------------------------------
# TAB 3: Guideline Management
# ----------------------------------------------------
with tab_guide:
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
            
            # 카테고리 선택 (Dropdown)
            selected_cat_view = st.selectbox("📂 조회할 카테고리", categories)
            
            # 선택된 카테고리 데이터 표시
            cat_data = df_guide[df_guide["category"] == selected_cat_view]
            
            if not cat_data.empty:
                for _, row in cat_data.iterrows():
                    with st.container(border=True):
                        st.caption(f"Original Input: {row['raw_input']}")
                        
                        # [NEW] 수정 가능한 텍스트 영역
                        # key를 유니크하게 생성 (g_edit_{id})
                        new_text = st.text_area(
                            "가이드라인 내용 (수정 가능)", 
                            value=row['refined_content'],
                            height=150,
                            key=f"g_edit_{row['id']}"
                        )
                        
                        col_btn1, col_btn2 = st.columns([1.5, 4.5])
                        with col_btn1:
                            if st.button("수정 저장", key=f"save_{row['id']}"):
                                update_guideline_content(row['id'], new_text)
                                st.success("수정 완료!")
                                time.sleep(1)
                                st.rerun()
                        # 삭제 기능은 나중에 추가 가능
            else:
                st.info("이 카테고리에는 등록된 가이드라인이 없습니다.")
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
            st.success("변환 완료! (필요 시 내용을 수정하세요)")
            st.text_area("정제된 가이드 (편집 가능)", key="temp_refined", height=300)
            
            if st.button("DB에 저장"):
                add_new_guideline(category, raw_input, st.session_state["temp_refined"])
                st.success("저장되었습니다!")
                del st.session_state["temp_refined"]
                st.rerun()

# ----------------------------------------------------
# TAB 4: Category Management - NOW Using tab_types
# ----------------------------------------------------
with tab_types:
    st.subheader("📑 상담 유형(Category) 관리")
    st.info("가이드라인 및 상담 분류에 사용되는 카테고리를 관리합니다. 삭제 시 'Unused' 처리되어 과거 데이터는 보존됩니다.")

    active_types = fetch_consultation_types()
    
    col_c1, col_c2 = st.columns([1, 1])
    
    with col_c1:
        st.markdown("#### 현재 활성 카테고리")
        # include_desc=True로 상세 정보 가져오기
        detailed_types = fetch_consultation_types(include_desc=True)
        
        # Fallback for list of strings (if DB migration pending/failed)
        if detailed_types and isinstance(detailed_types[0], str):
            for t in detailed_types:
                with st.container(border=True):
                    c_a, c_b = st.columns([3, 1])
                    c_a.write(f"**{t}**")
                    if c_b.button("삭제", key=f"del_{t}"):
                         if deactivate_consultation_type(t):
                             st.rerun()
        else:
            for t_obj in detailed_types:
                t_name = t_obj['name']
                t_desc = t_obj.get('description', '')
                with st.container(border=True):
                    c_a, c_b = st.columns([3, 1])
                    c_a.markdown(f"**{t_name}**")
                    if t_desc:
                        c_a.caption(f"└ {t_desc}")
                    
                    if c_b.button("삭제", key=f"del_{t_name}"):
                        if deactivate_consultation_type(t_name):
                            st.success(f"'{t_name}' 삭제 완료")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("삭제 실패")

    with col_c2:
        st.markdown("#### ➕ 카테고리 추가")
        new_cat = st.text_input("새 카테고리 명 (영문 권장)", placeholder="예: promotion")
        new_desc = st.text_input("설명 (AI 인식용)", placeholder="예: 프로모션, 이벤트, 쿠폰 관련 문의")
        
        if st.button("추가하기"):
            if not new_cat:
                st.error("이름을 입력하세요.")
            # 중복 체크 (이름만 비교)
            active_names = [t if isinstance(t, str) else t['name'] for t in detailed_types]
            
            if new_cat in active_names:
                st.error("이미 존재하는 카테고리입니다.")
            else:
                success, msg = add_consultation_type(new_cat, new_desc)
                if success:
                    st.success(f"'{new_cat}' 추가 완료!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"추가 실패: {msg}")

# ----------------------------------------------------
# TAB 5: Reference Management - NOW Using tab_refs
# ----------------------------------------------------
with tab_refs:
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
                    
                    if r.get('file_url'):
                        st.link_button("📥 원본 파일 보기 (Download)", r['file_url'])
                    
                    if st.button("삭제(Soft Delete)", key=f"del_ref_{r['id']}"):
                        if delete_reference(r['id']):
                            st.success("삭제됨")
                            time.sleep(1)
                            st.rerun()
        else:
            st.info("등록된 자료가 없습니다.")

    with col_ref_add:
        st.markdown("#### ➕ 새 자료 등록")
        
        # [NEW] 파일 업로드 기능
        uploaded_ref_file = st.file_uploader(
            "📂 파일로 불러오기 (PDF/Docx/Txt)", 
            type=["pdf", "docx", "txt"],
            help="파일을 드래그해서 넣으면 AI가 내용을 인식합니다.\n파일이 없다면 아래 '본문 (전체 내용)'에 직접 텍스트를 입력하셔도 됩니다."
        )
        
        if uploaded_ref_file:
            st.info("✅ 파일이 선택되었습니다. AI가 파일 내용을 직접 읽어 분석합니다.")
        
        with st.form("add_ref_form"):
            in_cat = st.selectbox("카테고리", ["common"] + active_types)
            in_title = st.text_input("제목", placeholder="예: 소비자 분쟁 해결 기준")
            
            # [MODIFIED] 텍스트 입력창은 이제 '선택 사항'이 됨
            in_content = st.text_area("보충 설명 (선택 사항 - 파일이 없는 경우 필수)", 
                                      height=150, 
                                      placeholder="직접 입력하거나, 파일에 대한 추가 설명을 적으세요.")
            
            st.caption("ℹ️ '등록 하기'를 누르면 AI가 **'어떤 상황에서 이 자료를 써야 하는지'**를 분석해 저장합니다.")
            
            submitted = st.form_submit_button("등록 하기")
            
            if submitted:
                if not uploaded_ref_file and not in_content:
                    st.error("파일을 업로드하거나 본문을 입력해야 합니다.")
                else:
                    file_url = None
                    file_bytes = None
                    mime_type = "application/pdf" # Default
                    
                    if uploaded_ref_file:
                        with st.spinner("파일을 저장소에 업로드 중..."):
                            ext = uploaded_ref_file.name.split('.')[-1].lower()
                            mime_type = "application/pdf" if ext == "pdf" else "text/plain" # Simple fallback
                            
                            uploaded_ref_file.seek(0)
                            file_bytes = uploaded_ref_file.getvalue()
                            
                            # Upload to Storage
                            file_url = upload_reference_file(file_bytes, ext)
                    
                    with st.spinner("AI가 사용 상황(Context)을 분석 중입니다..."):
                        # 파일이 있으면 파일 바이트 전달, 없으면 텍스트 전달
                        final_summary = generate_reference_usage_context(
                            content=in_content, 
                            file_data=file_bytes,
                            mime_type=mime_type
                        )
                    
                    # Content 저장: 파일이 있으면 텍스트가 비어있어도 됨.
                    # 하지만 DB에 뭔가는 넣어야 한다면...
                    content_to_save = in_content if in_content else "(첨부 파일 참조)"
                    
                    suc, msg = add_reference(in_cat, in_title, content_to_save, final_summary, file_url)
                    if suc:
                        st.success("등록 완료! (사용 가이드 포함)")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"실패: {msg}")