import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import requests

# 1. 페이지 기본 설정
st.set_page_config(
    page_title="전국 대학생 분포 지도",
    page_icon="🎓",
    layout="wide"
)

st.title("🎓 전국 시군구별 대학생 인구 비율 지도")
st.markdown("대한민국 시군구별 인구 대비 대학생 비중(%)을 보여주는 단계구분도(Choropleth Map)입니다.")

# 2. GeoJSON 로드 함수 (다중 백업 URL 적용)
@st.cache_data(ttl=3600)
def load_geojson():
    # 1차/2차 백업 GeoJSON URL 목록 (대한민국 시군구 행정구역)
    urls = [
        # 대한민국 시군구 GeoJSON (최신 행정구역 미러)
        "https://raw.githubusercontent.com/southkorea/southkorea-maps/master/kostat/2013/json/skorea_municipalities_2013_geo.json",
        # 대체 백업 URL (GADM 기반)
        "https://raw.githubusercontent.com/valentin212/korea-geojson/master/kr-all-cities-provinces.json"
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    for url in urls:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "features" in data and len(data["features"]) > 0:
                    return data
        except Exception:
            continue
            
    return None

@st.cache_data
def load_sample_data(geojson_data):
    """GeoJSON의 시군구 코드/이름을 기반으로 샘플 대학생 비율 데이터 생성"""
    if not geojson_data:
        return pd.DataFrame()
    
    features = geojson_data["features"]
    records = []
    
    np.random.seed(42)  # 재현 가능한 데이터
    
    for feature in features:
        props = feature["properties"]
        # GeoJSON 구조에 따라 코드/이름 키값 유연 처리
        code = props.get("code") or props.get("SIG_CD") or props.get("id") or str(np.random.randint(10000, 99999))
        name = props.get("name") or props.get("SIG_KOR_NM") or props.get("NL_NAME_2") or "지역"
        
        # 대학가 특성을 모사하기 위한 난수 생성 (3%~18% 사이 비율)
        college_ratio = np.round(np.random.beta(2, 5) * 20, 2)
        
        records.append({
            "code": code,
            "name": name,
            "college_ratio": college_ratio
        })
        
    return pd.DataFrame(records)

# 3. 데이터 준비 및 실행
with st.spinner("지도 데이터를 불러오는 중입니다..."):
    geojson = load_geojson()

if geojson:
    df = load_sample_data(geojson)
    
    # 사이드바 컨트롤
    st.sidebar.header("⚙️ 지도 설정")
    color_scale = st.sidebar.selectbox(
        "색상 테마 선택",
        ["YlOrRd", "Viridis", "Plasma", "Blues", "Reds"],
        index=0
    )
    
    min_ratio, max_ratio = float(df["college_ratio"].min()), float(df["college_ratio"].max())
    ratio_filter = st.sidebar.slider(
        "대학생 비율 필터 (%)",
        min_value=min_ratio,
        max_value=max_ratio,
        value=(min_ratio, max_ratio)
    )
    
    filtered_df = df[(df["college_ratio"] >= ratio_filter[0]) & (df["college_ratio"] <= ratio_filter[1])]
    
    # Feature ID 매핑 키 자동 판별
    sample_props = geojson["features"][0]["properties"]
    if "code" in sample_props:
        feature_key = "properties.code"
    elif "SIG_CD" in sample_props:
        feature_key = "properties.SIG_CD"
    else:
        feature_key = "properties.name"
        df["code"] = df["name"]

    # 4. Plotly Express 단계구분도 작성
    fig = px.choropleth_mapbox(
        filtered_df,
        geojson=geojson,
        locations="code",
        featureidkey=feature_key,
        color="college_ratio",
        color_continuous_scale=color_scale,
        range_color=(df["college_ratio"].min(), df["college_ratio"].max()),
        mapbox_style="carto-positron",
        zoom=6.2,
        center={"lat": 35.9, "lon": 127.7717},
        opacity=0.7,
        labels={"college_ratio": "대학생 비율 (%)", "name": "지역명", "code": "시군구코드"},
        hover_name="name",
        hover_data={"code": True, "college_ratio": ":.2f%"}
    )
    
    fig.update_layout(
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        height=650
    )
    
    # 5. 레이아웃 배치 (지도 & 데이터 테이블)
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.plotly_chart(fig, use_container_width=True)
        
    with col2:
        st.subheader("📊 주요 통계")
        st.metric("전국 평균 비율", f"{df['college_ratio'].mean():.2f}%")
        st.metric("최고 비율 지역", f"{df.loc[df['college_ratio'].idxmax()]['name']}", f"{df['college_ratio'].max():.2f}%")
        st.metric("최저 비율 지역", f"{df.loc[df['college_ratio'].idxmin()]['name']}", f"{df['college_ratio'].min():.2f}%")
        
        st.subheader("📋 선택 범위 데이터")
        st.dataframe(
            filtered_df[["name", "college_ratio"]].sort_values(by="college_ratio", ascending=False),
            hide_index=True,
            use_container_width=True
        )
else:
    st.error("GeoJSON 데이터를 불러오지 못했습니다. 프로젝트 폴더에 GeoJSON 파일을 직접 넣는 가장 확실한 방법을 권장합니다.")
