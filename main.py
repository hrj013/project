# main.py
# 전국 시군구별 고령화율(65세 이상 인구 비율)을 보여주는 Streamlit 앱

import io
import gzip
import requests
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


# ---------------------------------------------------------
# 기본 설정
# ---------------------------------------------------------

st.set_page_config(
    page_title="전국 시군구 고령화 지도",
    page_icon="🗺️",
    layout="wide",
)

POPULATION_URL = (
    "https://raw.githubusercontent.com/greatsong/modudata/"
    "main/data/population_yearly.csv.gz"
)

GEOJSON_URL = (
    "https://raw.githubusercontent.com/greatsong/modudata/"
    "main/data/boundaries/sigungu_kr.geojson"
)

# 고령화율을 나누는 5개 구간의 경계값
BREAKS = [0.19, 0.23, 0.28, 0.38]

# 지도에 사용할 5단계 색상
COLORS = [
    "#edf8fb",  # 가장 낮음
    "#b2e2e2",
    "#66c2a4",
    "#2ca25f",
    "#006d2c",  # 가장 높음
]

# 범례에 표시할 이름
CATEGORY_LABELS = [
    "19% 미만",
    "19% 이상 ~ 23% 미만",
    "23% 이상 ~ 28% 미만",
    "28% 이상 ~ 38% 미만",
    "38% 이상",
]


# ---------------------------------------------------------
# 데이터 불러오기
# ---------------------------------------------------------

@st.cache_data(show_spinner=False)
def load_population_data():
    """인구 CSV를 내려받아 읽습니다."""

    response = requests.get(POPULATION_URL, timeout=60)
    response.raise_for_status()

    # gzip으로 압축된 CSV를 메모리에서 바로 풉니다.
    csv_bytes = gzip.decompress(response.content)

    df = pd.read_csv(
        io.BytesIO(csv_bytes),
        dtype={"코드": "string"},  # 코드는 계산값이 아니라 식별자이므로 문자열로 읽습니다.
    )

    return df


@st.cache_data(show_spinner=False)
def load_geojson():
    """시군구 경계 GeoJSON을 내려받습니다."""

    response = requests.get(GEOJSON_URL, timeout=60)
    response.raise_for_status()

    return response.json()


# ---------------------------------------------------------
# 고령화율 계산
# ---------------------------------------------------------

def calculate_aging_rate(df):
    """
    최신 연도의 읍·면·동 인구를 시군구 단위로 합산한 뒤
    65세 이상 인구 비율을 계산합니다.
    """

    # 코드가 혹시 숫자로 변환되었더라도 0으로 시작하는 코드를 보존합니다.
    df["코드"] = df["코드"].astype("string").str.strip()

    # 연도는 숫자로 변환합니다.
    df["연도"] = pd.to_numeric(df["연도"], errors="coerce")

    # 가장 최신 연도만 사용합니다.
    latest_year = int(df["연도"].max())
    df = df[df["연도"] == latest_year].copy()

    # 행정동 코드의 앞 5자리가 시군구 코드입니다.
    df["시군구코드"] = df["코드"].str[:5]

    # 나이별 '계_' 열만 골라냅니다.
    # 예: 계_0세, 계_1세, ... 계_100세 이상
    total_age_columns = [
        column
        for column in df.columns
        if column.startswith("계_")
    ]

    # 65세 이상에 해당하는 '계_' 열만 골라냅니다.
    elderly_columns = []

    for column in total_age_columns:
        age_text = column.replace("계_", "").replace("세", "").strip()

        # '100세 이상' 같은 값은 100으로 처리합니다.
        if age_text == "100세 이상":
            age = 100
        else:
            try:
                age = int(age_text)
            except ValueError:
                continue

        if age >= 65:
            elderly_columns.append(column)

    # 읍·면·동별 전체 인구와 65세 이상 인구를 계산합니다.
    df["전체인구"] = df[total_age_columns].sum(axis=1, numeric_only=True)
    df["65세이상인구"] = df[elderly_columns].sum(axis=1, numeric_only=True)

    # 시군구 단위로 합산합니다.
    sigungu = (
        df.groupby("시군구코드", as_index=False)
        .agg(
            전체인구=("전체인구", "sum"),
            **{"65세이상인구": ("65세이상인구", "sum")},
        )
    )

    # 고령화율 = 65세 이상 인구 / 전체 인구
    sigungu["고령화율"] = (
        sigungu["65세이상인구"] / sigungu["전체인구"]
    )

    sigungu["고령화율(%)"] = sigungu["고령화율"] * 100

    sigungu["연도"] = latest_year

    return sigungu, latest_year


# ---------------------------------------------------------
# 5단계 구간 만들기
# ---------------------------------------------------------

def make_category(rate):
    """고령화율을 5개 구간 중 하나로 분류합니다."""

    if pd.isna(rate):
        return None

    if rate < BREAKS[0]:
        return CATEGORY_LABELS[0]
    elif rate < BREAKS[1]:
        return CATEGORY_LABELS[1]
    elif rate < BREAKS[2]:
        return CATEGORY_LABELS[2]
    elif rate < BREAKS[3]:
        return CATEGORY_LABELS[3]
    else:
        return CATEGORY_LABELS[4]


# ---------------------------------------------------------
# 화면
# ---------------------------------------------------------

st.title("🗺️ 전국 시군구 고령화 지도")
st.caption("65세 이상 인구 비율 · 최신 연도 기준")

try:
    with st.spinner("최신 인구 자료와 지도 경계를 불러오는 중입니다..."):
        population_df = load_population_data()
        geojson = load_geojson()

        aging_df, latest_year = calculate_aging_rate(population_df)

except Exception as e:
    st.error("데이터를 불러오는 중 문제가 발생했습니다.")
    st.exception(e)
    st.stop()


# ---------------------------------------------------------
# GeoJSON과 인구 데이터를 '코드'로 연결
# ---------------------------------------------------------

# GeoJSON의 코드도 문자열로 취급합니다.
for feature in geojson["features"]:
    properties = feature.get("properties", {})
    properties["코드"] = str(properties.get("코드", "")).zfill(5)

    feature["properties"] = properties

# 지도용 데이터에 구간 이름을 추가합니다.
aging_df["구간"] = aging_df["고령화율"].apply(make_category)

# Plotly에서 GeoJSON의 '코드'와 데이터의 '시군구코드'를 연결합니다.
aging_df["지도코드"] = aging_df["시군구코드"].astype(str).str.zfill(5)


# ---------------------------------------------------------
# 제목 및 간단한 설명
# ---------------------------------------------------------

st.subheader(f"{latest_year}년 시군구별 고령화율")

st.markdown(
    """
    **고령화율**은 해당 시군구의 전체 인구 중 **65세 이상 인구가 차지하는 비율**입니다.
    
    색이 진할수록 고령화율이 높습니다. 지도는 19%, 23%, 28%, 38%를
    경계로 5단계로 나누었습니다.
    """
)


# ---------------------------------------------------------
# 단계구분도
# ---------------------------------------------------------

fig = px.choropleth(
    aging_df,
    geojson=geojson,
    locations="지도코드",
    featureidkey="properties.코드",
    color="구간",
    category_orders={
        "구간": CATEGORY_LABELS
    },
    color_discrete_map={
        CATEGORY_LABELS[0]: COLORS[0],
        CATEGORY_LABELS[1]: COLORS[1],
        CATEGORY_LABELS[2]: COLORS[2],
        CATEGORY_LABELS[3]: COLORS[3],
        CATEGORY_LABELS[4]: COLORS[4],
    },
    custom_data=[
        "시군구코드",
        "고령화율(%)",
        "연도",
    ],
    labels={
        "구간": "고령화율 구간",
    },
)

# 마우스를 올렸을 때 보여줄 정보
fig.update_traces(
    hovertemplate=(
        "<b>%{location}</b><br>"
        "고령화율: %{customdata[1]:.2f}%"
        "<extra></extra>"
    ),
    marker_line_color="white",
    marker_line_width=0.6,
)

# GeoJSON 전체를 한반도 영역에 맞춰 표시합니다.
fig.update_geos(
    fitbounds="locations",
    visible=False,
    projection_type="mercator",
)

fig.update_layout(
    height=720,
    margin=dict(l=0, r=0, t=20, b=0),
    legend_title_text="고령화율",
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=-0.02,
        xanchor="center",
        x=0.5,
    ),
)

st.plotly_chart(
    fig,
    use_container_width=True,
    config={
        "displayModeBar": False,
        "scrollZoom": False,
    },
)


# ---------------------------------------------------------
# 순위 표
# ---------------------------------------------------------

st.subheader("시군구별 고령화율")

# 표에 표시할 열을 준비합니다.
table_columns = [
    "시도",
    "시군구",
    "고령화율(%)",
    "65세이상인구",
    "전체인구",
]

# GeoJSON의 시군구 이름과 시도 이름을 코드로 가져옵니다.
geo_rows = []

for feature in geojson["features"]:
    properties = feature.get("properties", {})

    code = str(properties.get("코드", "")).zfill(5)

    geo_rows.append(
        {
            "지도코드": code,
            "시군구": properties.get("시군구", ""),
            "시도": properties.get("시도", ""),
        }
    )

geo_df = pd.DataFrame(geo_rows)

ranking_df = aging_df.merge(
    geo_df,
    on="지도코드",
    how="left",
)

# 숫자를 보기 좋게 정리합니다.
ranking_df["고령화율(%)"] = ranking_df["고령화율(%)"].round(2)

ranking_df["65세이상인구"] = (
    ranking_df["65세이상인구"]
    .round()
    .astype("Int64")
)

ranking_df["전체인구"] = (
    ranking_df["전체인구"]
    .round()
    .astype("Int64")
)


# 높은 곳 10개 / 낮은 곳 10개
high_10 = (
    ranking_df
    .sort_values("고령화율(%)", ascending=False)
    .head(10)
    .copy()
)

low_10 = (
    ranking_df
    .sort_values("고령화율(%)", ascending=True)
    .head(10)
    .copy()
)


# ---------------------------------------------------------
# 두 표를 나란히 표시
# ---------------------------------------------------------

left, right = st.columns(2)

with left:
    st.markdown("### 🔴 고령화율 높은 곳 10개")

    high_display = high_10[
        ["시도", "시군구", "고령화율(%)"]
    ].reset_index(drop=True)

    high_display.index = high_display.index + 1

    st.dataframe(
        high_display,
        use_container_width=True,
        column_config={
            "시도": "시도",
            "시군구": "시군구",
            "고령화율(%)": st.column_config.NumberColumn(
                "고령화율 (%)",
                format="%.2f",
            ),
        },
    )


with right:
    st.markdown("### 🔵 고령화율 낮은 곳 10개")

    low_display = low_10[
        ["시도", "시군구", "고령화율(%)"]
    ].reset_index(drop=True)

    low_display.index = low_display.index + 1

    st.dataframe(
        low_display,
        use_container_width=True,
        column_config={
            "시도": "시도",
            "시군구": "시군구",
            "고령화율(%)": st.column_config.NumberColumn(
                "고령화율 (%)",
                format="%.2f",
            ),
        },
    )


# ---------------------------------------------------------
# 데이터 기준 안내
# ---------------------------------------------------------

st.caption(
    f"자료: 제공된 전국 읍·면·동 인구자료를 시군구 단위로 합산하여 계산 · {latest_year}년 기준"
)

