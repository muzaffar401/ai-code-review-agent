import streamlit as st
from streamlit import session_state as state
from datetime import datetime
import google.generativeai as genai
import traceback
from contextlib import redirect_stdout
from io import StringIO
import ast
import re

# --- Page Config (MUST BE FIRST) ---
st.set_page_config(
    page_title="AI Code Review Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom CSS for Dark Gradient UI ---
st.markdown("""
<style>
    /* Main container */
    .stApp {
        background: linear-gradient(135deg, #121212 0%, #1e1e1e 100%);
        color: #e0e0e0;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(195deg, #0f2027 0%, #203a43 50%, #2c5364 100%);
        color: white;
    }
    
    /* Text area */
    .stTextArea textarea {
        background-color: #2d2d2d !important;
        color: #f0f0f0 !important;
        border: 1px solid #444 !important;
        border-radius: 12px;
        font-family: 'Fira Code', monospace;
        box-shadow: 0 2px 10px rgba(0,0,0,0.2);
    }
    
    /* Text area placeholder */
    .stTextArea textarea::placeholder {
        color: #ffffff !important;
        opacity: 0.7 !important;
    }
    
    /* Buttons */
    .stButton>button {
        border-radius: 12px;
        border: none;
        font-weight: 500;
        transition: all 0.3s ease;
        box-shadow: 0 2px 5px rgba(0,0,0,0.2);
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(0,0,0,0.3);
    }
    
    /* Primary button (Analyze Code) */
    div[data-testid="stButton"] > button[kind="primary"] {
        background: linear-gradient(135deg, #4285F4 0%, #34A853 100%) !important;
        color: white !important;
    }
    
    /* Secondary buttons (Run Code, Clear) */
    div[data-testid="stButton"] > button:not([kind="primary"]) {
        background: #121212 !important;
        color: white !important;
        border: 1px solid #444 !important;
    }
    
    /* Tabs */
    [data-testid="stTab"] {
        background: #2d2d2d;
        border-radius: 12px;
        padding: 10px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        border: 1px solid #444;
    }
    
    /* Tab buttons */
    button[data-baseweb="tab"] {
        color: #aaa !important;
        font-weight: 500;
        transition: all 0.3s ease;
    }
    
    button[data-baseweb="tab"]:hover {
        color: #fff !important;
        background-color: rgba(255,255,255,0.1) !important;
    }
    
    button[aria-selected="true"] {
        color: #fff !important;
        background-color: rgba(66, 133, 244, 0.2) !important;
    }
    
    /* Code blocks */
    pre {
        background-color: #1e1e1e !important;
        border-radius: 12px !important;
        border: 1px solid #444 !important;
    }
    
    /* Expanders */
    [data-testid="stExpander"] {
        background: #2d2d2d;
        border-radius: 12px;
        border: 1px solid #444;
    }
    
    /* Success message */
    .stAlert .st-emotion-cache-1hynsf2 {
        background: linear-gradient(135deg, #34A85320 0%, #34A85340 100%);
        border: 1px solid #34A853;
        border-radius: 12px;
    }
    
    /* Error message */
    .stAlert .st-emotion-cache-1m1ta7z {
        background: linear-gradient(135deg, #EA433520 0%, #EA433540 100%);
        border: 1px solid #EA4335;
        border-radius: 12px;
    }
    
    /* Info message */
    .stAlert .st-emotion-cache-1uixxvy {
        background: linear-gradient(135deg, #4285F420 0%, #4285F440 100%);
        border: 1px solid #4285F4;
        border-radius: 12px;
    }
    
    /* Container borders */
    [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 12px;
    }
    
    /* Markdown headers */
    h1, h2, h3, h4, h5, h6 {
        color: #f0f0f0 !important;
    }
    
    /* Markdown text */
    p, li {
        color: #e0e0e0 !important;
    }

    .stAppHeader{
    
    }
    
    /* Code input label */
    .stTextArea label p {
        color: #f0f0f0 !important;
        font-size: 16px !important;
        font-weight: 500 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- Session State Initialization ---
if 'code_submissions' not in state:
    state.code_submissions = []
if 'current_code' not in state:
    state.current_code = ""
if 'current_review' not in state:
    state.current_review = ""
if 'execution_output' not in state:
    state.execution_output = None
if 'selected_submission' not in state:
    state.selected_submission = None
if 'suggested_code' not in state:
    state.suggested_code = None

# --- Gemini Setup ---
GEMINI_API_KEY = st.secrets["gemini"]["api_key"]
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- Constants ---
MAX_CODE_LENGTH = 2000

# --- Core Functions ---
def generate_code_review(code):
    """Generate AI-powered code review and fix suggestion."""
    prompt = f"""
You are a senior Python developer. Review the following code thoroughly. 
Then suggest fixes for bugs, improvements, and best practices.

Focus on:
- Correctness
- Performance
- Readability
- Security

Return markdown output with clear sections:
1. Summary
2. Issues Found
3. Suggestions
4. Suggested Fixed Code (as a code block)
   
Code:
```python
{code}
```"""

    try:
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.3,
                "max_output_tokens": 2000
            }
        )
        return response.text
    except Exception as e:
        st.error(f"⚠️ Review generation failed: {str(e)}")
        return None

def extract_fixed_code_from_review(review_text):
    """Extract the fixed code block from AI response."""
    match = re.search(r'```python\n(.*?)```', review_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None

def execute_python_code(code):
    """Safely execute Python code with error handling."""
    if len(code) > MAX_CODE_LENGTH:
        return {
            "status": "error",
            "error": f"Code exceeds {MAX_CODE_LENGTH} character limit"
        }

    output = StringIO()
    try:
        ast.parse(code)
        with redirect_stdout(output):
            local_vars = {}
            exec(code, {}, local_vars)
            return {
                "status": "success",
                "output": output.getvalue(),
                "variables": {k: v for k, v in local_vars.items() if not k.startswith('_')}
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "details": traceback.format_exc()
        }

# --- UI Sidebar ---
with st.sidebar:
    st.markdown("""
    <div style="padding: 20px 0 30px 0; text-align: center;">
        <h1 style="color: white; font-size: 28px; margin-bottom: 0;">🔮 CodeGenius</h1>
        <p style="color: #a1a9b5; font-size: 14px; margin-top: 0;">AI-Powered Code Review</p>
        <div style="height: 3px; background: linear-gradient(90deg, #4285F4 0%, #34A853 50%, #FBBC05 100%); 
            margin: 10px auto; width: 80%; border-radius: 3px;"></div>
    </div>
    """, unsafe_allow_html=True)
    
    with st.expander("📚 History", expanded=True):
        if state.code_submissions:
            for idx, sub in enumerate(reversed(state.code_submissions)):
                btn_style = """
                background: linear-gradient(135deg, #2d2d2d 0%, #1e1e1e 100%);
                border: 1px solid #444;
                border-radius: 8px;
                padding: 8px;
                margin: 4px 0;
                text-align: left;
                """
                if st.button(
                    f"📌 {sub['timestamp']}",
                    key=f"hist_{idx}",
                    help=f"{len(sub['code'].splitlines())} lines",
                    use_container_width=True
                ):
                    state.selected_submission = len(state.code_submissions) - idx - 1
                    state.current_code = sub["code"]
                    state.current_review = sub["review"]
                    state.execution_output = sub.get("execution_output")
                    state.suggested_code = sub.get("suggested_code")
                    st.rerun()
        else:
            st.info("No history yet", icon="ℹ️")

# --- Main UI ---
st.markdown("""
<div style="padding: 20px 0 10px 0;">
    <h1 style="color: #f0f0f0; font-size: 36px; margin-bottom: 0;">🤖 AI Code Review Agent</h1>
    <p style="color: #a1a9b5; font-size: 16px; margin-top: 0;">Get instant AI-powered code analysis and improvement suggestions</p>
    <div style="height: 3px; background: linear-gradient(90deg, #4285F4 0%, #34A853 50%, #FBBC05 100%); 
        margin: 10px 0; width: 100%; border-radius: 3px;"></div>
</div>
""", unsafe_allow_html=True)

# --- Code Input ---
with st.container():
    st.markdown("### ✍️ Your Python Code")
    code = st.text_area(
        "Paste your Python code below",
        height=300,
        value=state.current_code,
        key="code_input",
        placeholder="def hello():\n    print('Hello World!')",
        label_visibility="collapsed"
    )

# --- Action Buttons ---
col1, col2, col3 = st.columns(3)
with col1:
    analyze_btn = st.button(
        "🔍 Analyze Code", 
        type="primary", 
        use_container_width=True,
        help="Get AI-powered code review"
    )

with col2:
    run_btn = st.button(
        "▶️ Run Code", 
        use_container_width=True,
        help="Execute your Python code"
    )

with col3:
    clear_btn = st.button(
        "🧹 Clear", 
        use_container_width=True,
        help="Reset the editor"
    )

if analyze_btn:
    if code.strip():
        with st.spinner("🧠 Analyzing your code..."):
            review = generate_code_review(code)
            if review:
                suggested = extract_fixed_code_from_review(review)
                state.current_review = review
                state.suggested_code = suggested
                submission = {
                    "code": code,
                    "review": review,
                    "timestamp": datetime.now().strftime("%H:%M %Y-%m-%d"),
                    "execution_output": None,
                    "suggested_code": suggested
                }
                state.code_submissions.append(submission)
                st.rerun()
    else:
        st.warning("Please enter code first", icon="⚠️")

if run_btn:
    if code.strip():
        with st.spinner("⚡ Executing code..."):
            state.execution_output = execute_python_code(code)
            st.rerun()
    else:
        st.warning("No code to execute", icon="⚠️")

if clear_btn:
    state.current_code = ""
    state.current_review = ""
    state.execution_output = None
    state.suggested_code = None
    st.rerun()

# --- Results Display ---
if state.current_review or state.execution_output:
    tab1, tab2 = st.tabs(["📝 AI Review Analysis", "🖥️ Code Execution"])

    with tab1:
        if state.current_review:
            with st.expander("🔍 Detailed Review", expanded=True):
                st.markdown(state.current_review)

            if state.suggested_code:
                st.markdown("### 💡 Suggested Improvements")
                with st.container(border=True):
                    st.code(state.suggested_code, language="python")
                    if st.button(
                        "🛠️ Apply Suggested Fix", 
                        type="primary",
                        use_container_width=True,
                        key="apply_fix"
                    ):
                        state.current_code = state.suggested_code
                        st.rerun()
        else:
            st.info("No review generated yet", icon="ℹ️")

    with tab2:
        if state.execution_output:
            if state.execution_output["status"] == "success":
                st.success("✅ Execution Successful", icon="✅")
                with st.container(border=True):
                    st.code(state.execution_output["output"], language="python")
                if state.execution_output["variables"]:
                    with st.expander("📊 Variable Inspector"):
                        st.json(state.execution_output["variables"])
            else:
                st.error("❌ Execution Failed", icon="❌")
                st.error(state.execution_output.get("error", "Unknown error"))
                if "details" in state.execution_output:
                    with st.container(border=True):
                        st.code(state.execution_output["details"], language="python")
        else:
            st.info("No execution results available", icon="ℹ️")

# --- Footer ---
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #a1a9b5; font-size: 14px; padding: 20px 0;">
    <p>✨ <strong>Pro Tips:</strong> Keep code under 2000 chars • Apply fixes with one click • Revisit from history</p>
    <p>🤖 Powered by Gemini Flash AI • v2.1</p>
</div>
""", unsafe_allow_html=True)