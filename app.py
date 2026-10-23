import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Social Media Account Analyzer",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Social Media Account Analysis Tool")
st.markdown("Enter any YouTube handle (e.g., `@MrBeast`, `@veritasium`, `@GoogleDevelopers`) or Channel ID to audit performance, engagement rates, and content trends.")

# --- SIDEBAR CONFIGURATION (AUTOMATED SECRETS CHECK) ---
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Automatically try loading the API key from Streamlit Secrets
    try:
        api_key = st.secrets["YOUTUBE_API_KEY"]
        st.success("🔒 API Key loaded securely from Cloud Secrets.")
    except Exception:
        # Fallback to text input if secrets are not configured locally
        api_key = st.text_input("YouTube Data API v3 Key", type="password", help="Paste the API key from Google Cloud Console")
        
    max_videos = st.slider("Number of Recent Videos to Analyze", min_value=10, max_value=50, value=25, step=5)
    st.caption("Uses only 3 quota units per search (Free limit: 10,000/day).")

# --- CORE DATA FETCHING ENGINE ---
@st.cache_data(ttl=600, show_spinner=False)
def fetch_channel_and_videos(identifier: str, api_key: str, max_results: int):
    identifier = identifier.strip()
    
    # Determine whether user entered a Handle (@name), Channel ID (UC...), or URL
    if "youtube.com/" in identifier:
        if "@" in identifier:
            identifier = "@" + identifier.split("@")[-1].split("/")[0].split("?")[0]
        elif "/channel/" in identifier:
            identifier = identifier.split("/channel/")[-1].split("/")[0].split("?")[0]

    base_url = "https://www.googleapis.com/youtube/v3"
    
    # 1. Fetch Channel Profile & Statistics
    params = {
        "part": "snippet,statistics,contentDetails",
        "key": api_key
    }
    if identifier.startswith("UC") and len(identifier) == 24:
        params["id"] = identifier
    else:
        handle = identifier if identifier.startswith("@") else f"@{identifier}"
        params["forHandle"] = handle

    ch_response = requests.get(f"{base_url}/channels", params=params, timeout=10)
    if ch_response.status_code != 200:
        err_msg = ch_response.json().get("error", {}).get("message", "Unknown API Error")
        return None, f"API Error ({ch_response.status_code}): {err_msg}"

    ch_data = ch_response.json()
    if not ch_data.get("items"):
        return None, f"No channel found for '{identifier}'. Check the spelling or try the exact @handle."

    channel = ch_data["items"][0]
    uploads_playlist_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]

    # 2. Fetch Recent Video IDs from Uploads Playlist
    pl_params = {
        "part": "contentDetails",
        "playlistId": uploads_playlist_id,
        "maxResults": max_results,
        "key": api_key
    }
    pl_response = requests.get(f"{base_url}/playlistItems", params=pl_params, timeout=10)
    if pl_response.status_code != 200:
        return None, "Could not fetch the video playlist for this channel."

    pl_items = pl_response.json().get("items", [])
    video_ids = [item["contentDetails"]["videoId"] for item in pl_items]

    if not video_ids:
        return {"channel": channel, "videos_df": pd.DataFrame()}, None

    # 3. Fetch Detailed Video Statistics in a Single Batch Call
    vid_params = {
        "part": "snippet,statistics,contentDetails",
        "id": ",".join(video_ids),
        "key": api_key
    }
    vid_response = requests.get(f"{base_url}/videos", params=vid_params, timeout=10)
    vid_items = vid_response.json().get("items", [])

    video_rows = []
    for v in vid_items:
        snippet = v.get("snippet", {})
        stats = v.get("statistics", {})

        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))
        comments = int(stats.get("commentCount", 0))

        # Engagement Rate per Video = (Likes + Comments) / Views * 100
        eng_rate = round(((likes + comments) / views) * 100, 2) if views > 0 else 0.0
        
        pub_date = datetime.strptime(snippet["publishedAt"], "%Y-%m-%dT%H:%M:%SZ")

        video_rows.append({
            "Video ID": v["id"],
            "Title": snippet.get("title", "Untitled"),
            "Published Date": pub_date.strftime("%Y-%m-%d"),
            "Day of Week": pub_date.strftime("%A"),
            "Views": views,
            "Likes": likes,
            "Comments": comments,
            "Engagement Rate (%)": eng_rate,
            "URL": f"https://www.youtube.com/watch?v={v['id']}"
        })

    df = pd.DataFrame(video_rows)
    return {"channel": channel, "videos_df": df}, None


# --- USER INTERFACE & SEARCH ---
col_input, col_btn = st.columns([4, 1])
with col_input:
    target_account = st.text_input("Account Handle or Channel ID", value="@mkbhd", label_visibility="collapsed", placeholder="Enter @handle (e.g., @mkbhd)")
with col_btn:
    analyze_clicked = st.button("🔍 Analyze Account", use_container_width=True, type="primary")

if analyze_clicked:
    if not api_key:
        st.error("⚠️ Please enter your YouTube Data API v3 Key in the left sidebar first.")
    elif not target_account.strip():
        st.warning("⚠️ Please enter a valid channel handle.")
    else:
        with st.spinner(f"Fetching live data for {target_account}..."):
            data, error = fetch_channel_and_videos(target_account, api_key, max_videos)

        if error:
            st.error(error)
        elif data:
            ch = data["channel"]
            df = data["videos_df"]
            ch_stats = ch["statistics"]
            ch_snippet = ch["snippet"]

            # --- PROFILE HEADER ---
            st.divider()
            prof_col1, prof_col2 = st.columns([1, 7])
            with prof_col1:
                thumb_url = ch_snippet["thumbnails"]["high"]["url"]
                st.image(thumb_url, width=110)
            with prof_col2:
                st.subheader(f"{ch_snippet['title']} ({ch_snippet.get('customUrl', '')})")
                st.write(ch_snippet.get("description", "")[:250] + "...")

            # --- KPI METRICS ---
            subscribers = int(ch_stats.get("subscriberCount", 0))
            total_views = int(ch_stats.get("viewCount", 0))
            total_videos = int(ch_stats.get("videoCount", 0))
            avg_eng = round(df["Engagement Rate (%)"].mean(), 2) if not df.empty else 0.0
            avg_views = int(df["Views"].mean()) if not df.empty else 0

            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Subscribers", f"{subscribers:,}")
            m2.metric("Total Channel Views", f"{total_views:,}")
            m3.metric("Total Videos", f"{total_videos:,}")
            m4.metric("Avg Views (Recent)", f"{avg_views:,}")
            m5.metric("Avg Engagement Rate", f"{avg_eng}%")

            if not df.empty:
                st.divider()

                # --- CHARTS SECTION ---
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("#### 📈 Views Trend (Recent Uploads)")
                    df_sorted = df.sort_values("Published Date")
                    fig_views = px.bar(
                        df_sorted,
                        x="Published Date",
                        y="Views",
                        hover_data=["Title", "Likes", "Comments"],
                        color="Engagement Rate (%)",
                        color_continuous_scale="Viridis"
                    )
                    st.plotly_chart(fig_views, use_container_width=True)

                with c2:
                    st.markdown("#### 🎯 Best Day to Post (Avg Views by Day)")
                    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                    day_df = df.groupby("Day of Week", as_index=False)["Views"].mean()
                    day_df["Day of Week"] = pd.Categorical(day_df["Day of Week"], categories=day_order, ordered=True)
                    day_df = day_df.sort_values("Day of Week")
                    fig_days = px.bar(
                        day_df,
                        x="Day of Week",
                        y="Views",
                        color="Views",
                        color_continuous_scale="Blues"
                    )
                    st.plotly_chart(fig_days, use_container_width=True)

                # --- AUTOMATED INSIGHTS ---
                best_vid = df.loc[df["Views"].idxmax()]
                best_eng_vid = df.loc[df["Engagement Rate (%)"].idxmax()]
                st.info(
                    f"💡 **Key Audit Takeaways:**\n"
                    f"- **Highest Reach Video:** *{best_vid['Title']}* ({best_vid['Views']:,} views)\n"
                    f"- **Most Engaging Video:** *{best_eng_vid['Title']}* ({best_eng_vid['Engagement Rate (%)']}% engagement rate)\n"
                    f"- **Views-to-Subscriber Ratio:** {round((avg_views / subscribers) * 100, 1) if subscribers else 0}% on recent uploads"
                )

                # --- DATA TABLE & CSV EXPORT ---
                st.markdown("#### 📋 Detailed Post Performance Breakdown")
                st.dataframe(
                    df,
                    column_config={
                        "URL": st.column_config.LinkColumn("Watch Link"),
                        "Views": st.column_config.NumberColumn(format="%d"),
                        "Likes": st.column_config.NumberColumn(format="%d"),
                        "Comments": st.column_config.NumberColumn(format="%d"),
                    },
                    hide_index=True,
                    use_container_width=True
                )

                csv_data = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="📥 Download Full Audit Report (CSV)",
                    data=csv_data,
                    file_name=f"{target_account.replace('@', '')}_audit_report.csv",
                    mime="text/csv"
                )
