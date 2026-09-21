import io
import gzip
import requests
import pandas as pd
import plotly.express as px
import streamlit as st


# =========================================================
# 기본 설정
# =========================================================

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

# 5단계 구간의 경계
BREAKS = [19, 23, 28, 38]

# 낮은 값 → 높은 값 순서
COLORS = [
    "#e8f5e9",
    "#a5d6a7",
    "#66bb6a",
    "#2e7d32",
    "#0b3d1e",
]

CATEGORIES = [
    "19% 미만",
    "19% 이상 ~ 23% 미만",
    "23% 이상 ~ 28% 미만",
    "28% 이상 ~ 38% 미만",
    "38% 이상",
]


# =========================================================
# 인구 데이터 불러오기
# =========================================================

@st.cache_data(show_spinner=False)
def load_population():
    """압축된 CSV를 인터넷에서 받아옵니다."""

    response = requests.get(POPULATION_URL, timeout=120)
    response.raise_for_status()

    # gzip 압축을 풉니다.
    raw = gzip.decompress(response.content)

    # 코드 열은 반드시 문자열로 읽습니다.
    df = pd.read_csv(
        io.BytesIO(raw),
        dtype={"코드": "string"},
    )

    return df


# =========================================================
# 지도 경계 불러오기
# =========================================================

@st.cache_data(show_spinner=False)
def load_geojson():
    """시군구 경계 GeoJSON을 받아옵니다."""

    response = requests.get(GEOJSON_URL, timeout=120)
    response.raise_for_status()

    return response.json()


# =========================================================
# 고령화율 계산
# =========================================================

def calculate_aging_rate(df):
    """읍·면·동 데이터를 시군구로 합쳐 고령화율을 계산합니다."""

    df = df.copy()

    # 코드가 숫자로 바뀌지 않도록 문자열로 유지합니다.
    df["코드"] = (
        df["코드"]
        .astype("string")
        .str.strip()
        .str.zfill(10)
    )

    # 연도 숫자화
    df["연도"] = pd.to_numeric(
        df["연도"],
        errors="coerce",
    )

    # 가장 최신 연도
    latest_year = int(df["연도"].max())

    df = df[df["연도"] == latest_year].copy()

    # 행정동 코드 앞 5자리가 시군구 코드
    df["시군구코드"] = df["코드"].str[:5]

    # 전체 인구에 해당하는 '계_' 열
    total_columns = [
        c
        for c in df.columns
        if c.startswith("계_")
    ]

    # 65세 이상 열
    elderly_columns = []

    for column in total_columns:
        age_text = column.replace("계_", "").strip()

        if age_text == "100세 이상":
            age = 100
        elif age_text.endswith("세"):
            try:
                age = int(age_text[:-1])
            except ValueError:
                continue
        else:
            continue

        if age >= 65:
            elderly_columns.append(column)

    if not elderly_columns:
        raise ValueError("65세 이상 인구 열을 찾지 못했습니다.")

    # 숫자로 안전하게 변환
    for column in total_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        ).fillna(0)

    # 읍·면·동별 전체 인구
    df["전체인구"] = df[total_columns].sum(axis=1)

    # 읍·면·동별 65세 이상 인구
    df["65세이상인구"] = df[elderly_columns].sum(axis=1)

    # 시군구 단위로 합산
    result = (
        df.groupby("시군구코드", as_index=False)
        .agg(
            전체인구=("전체인구", "sum"),
            **{
                "65세이상인구": (
                    "65세이상인구",
                    "sum",
                )
            },
        )
    )

    # 고령화율(%)
    result["고령화율"] = (
        result["65세이상인구"]
        / result["전체인구"]
        * 100
    )

    result["연도"] = latest_year

    return result, latest_year


# =========================================================
# 고령화율을 5개 구간으로 변환
# =========================================================

def classify_aging_rate(value):
    if pd.isna(value):
        return "자료 없음"

    if value < 19:
        return CATEGORIES[0]

    if value < 23:
        return CATEGORIES[1]

    if value < 28:
        return CATEGORIES[2]

    if value < 38:
        return CATEGORIES[3]

    return CATEGORIES[4]


# =========================================================
# 프로그램 시작
# =========================================================

st.title("🗺️ 전국 시군구 고령화 지도")

try:
    with st.spinner("인구 데이터와 지도 경계를 불러오는 중입니다..."):
        population = load_population()
        geojson = load_geojson()

        aging, latest_year = calculate_aging_rate(
            population
        )

except Exception as e:
    st.error("데이터를 불러오지 못했습니다.")
    st.code(str(e))
    st.stop()


# =========================================================
# GeoJSON에서 시군구 코드 추출
# =========================================================

geo_rows = []

for feature in geojson.get("features", []):
    properties = feature.get("properties", {})

    # 경계 데이터의 코드도 문자열로 통일
    code = str(
        properties.get("코드", "")
    ).strip().zfill(5)

    geo_rows.append(
        {
            "지도코드": code,
            "시군구": properties.get("시군구", ""),
            "시도": properties.get("시도", ""),
        }
    )

geo_info = pd.DataFrame(geo_rows)


# =========================================================
# 인구 데이터 + 지도 이름을 코드로 연결
# =========================================================

aging["지도코드"] = (
    aging["시군구코드"]
    .astype("string")
    .str.strip()
    .str.zfill(5)
)

map_data = aging.merge(
    geo_info,
    on="지도코드",
    how="left",
)

# 구간 이름
map_data["구간"] = map_data["고령화율"].apply(
    classify_aging_rate
)

# 지도에 실제로 존재하는 코드만 확인
map_data = map_data[
    map_data["시군구"].notna()
].copy()


# =========================================================
# 지도
# =========================================================

st.subheader(f"{latest_year}년 시군구별 65세 이상 인구 비율")

st.caption(
    "색이 진할수록 65세 이상 인구 비율이 높습니다. "
    "지도 경계는 시군구 코드로 연결했습니다."
)

fig = px.choropleth(
    map_data,
    geojson=geojson,
    locations="지도코드",
    featureidkey="properties.코드",
    color="구간",
    category_orders={
        "구간": CATEGORIES
    },
    color_discrete_map={
        CATEGORIES[0]: COLORS[0],
        CATEGORIES[1]: COLORS[1],
        CATEGORIES[2]: COLORS[2],
        CATEGORIES[3]: COLORS[3],
        CATEGORIES[4]: COLORS[4],
    },
    custom_data=[
        "시군구",
        "시도",
        "고령화율",
    ],
)

# 마우스를 올렸을 때 표시되는 내용
fig.update_traces(
    hovertemplate=(
        "<b>%{customdata[0]}</b><br>"
        "시도: %{customdata[1]}<br>"
        "고령화율: %{customdata[2]:.2f}%"
        "<extra></extra>"
    ),
    marker_line_color="#777777",
    marker_line_width=0.5,
)

# 배경 지도 타일 없이 GeoJSON만 표시
fig.update_geos(
    visible=False,
    projection_type="mercator",
    fitbounds="geojson",
)

fig.update_layout(
    height=700,
    margin=dict(
        l=0,
        r=0,
        t=10,
        b=20,
    ),
    legend_title_text="고령화율",
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=-0.03,
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


# =========================================================
# 순위 데이터
# =========================================================

ranking = map_data.copy()

ranking["고령화율(%)"] = ranking[
    "고령화율"
].round(2)

ranking["65세이상인구"] = (
    ranking["65세이상인구"]
    .round()
    .astype("int64")
)

ranking["전체인구"] = (
    ranking["전체인구"]
    .round()
    .astype("int64")
)


high_10 = (
    ranking
    .sort_values(
        "고령화율",
        ascending=False,
    )
    .head(10)
)

low_10 = (
    ranking
    .sort_values(
        "고령화율",
        ascending=True,
    )
    .head(10)
)


# =========================================================
# 표 두 개
# =========================================================

st.subheader("시군구별 고령화율 순위")

left, right = st.columns(2)

with left:

    st.markdown("### 🔴 고령화율 높은 곳 10개")

    high_table = high_10[
        [
            "시도",
            "시군구",
            "고령화율(%)",
        ]
    ].reset_index(drop=True)

    high_table.index = high_table.index + 1

    st.dataframe(
        high_table,
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

    low_table = low_10[
        [
            "시도",
            "시군구",
            "고령화율(%)",
        ]
    ].reset_index(drop=True)

    low_table.index = low_table.index + 1

    st.dataframe(
        low_table,
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


# =========================================================
# 하단 안내
# =========================================================

st.caption(
    f"자료: 제공된 전국 읍·면·동 인구자료 · {latest_year}년 기준"
)
