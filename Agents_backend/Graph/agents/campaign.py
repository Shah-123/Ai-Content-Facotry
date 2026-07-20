from concurrent.futures import ThreadPoolExecutor
from langchain_core.messages import SystemMessage, HumanMessage

from Graph.state import State
from .utils import logger, llm, _job, _emit

# ✅ FIX #10: Summarize the full blog into a structured brief BEFORE passing
# to campaign agents. Previously blog_post[:4000] was used, which for a
# 3000-word blog only covered ~600 words — roughly just the introduction.
# Campaign agents were writing LinkedIn posts, emails, and landing pages
# based entirely on the intro, missing all core arguments and the CTA.

CAMPAIGN_BRIEF_SYSTEM = """You are an expert B2B and consumer content strategist.
Read the full blog post and extract a high-fidelity, structured campaign brief.

Return EXACTLY this format — no extra text, no intros/outros:

TITLE: [exact blog title]
CORE_PROBLEM: [1 sentence — what is the exact pain point or tension solved?]
CORE_TENSION: [1 sentence — what is the contrarian or surprising viewpoint in the post?]
KEY_ARGUMENTS:
- [argument 1 - with specific context/mechanics]
- [argument 2 - with specific context/mechanics]
- [argument 3 - with specific context/mechanics]
KEY_STATS:
- [compelling stat/fact with source name & URL if present in evidence, e.g. "84% of developers struggle with X (Source: domain.com/url)"]
- [second compelling stat/fact with source & URL]
- [third compelling stat/fact with source & URL]
PRACTICAL_TIPS:
- [highly actionable tip 1 - starting with an action verb]
- [highly actionable tip 2 - starting with an action verb]
- [highly actionable tip 3 - starting with an action verb]
PRIMARY_CTA: [1 sentence — exact next action for reader]
TARGET_AUDIENCE: [who is this written for — specify role and skill level]
TONE: [what is the writing tone?]
"""



def _build_campaign_brief(blog_post: str, topic: str, evidence: list) -> str:
    """
    Summarizes the full blog into a structured brief for campaign agents.
    Uses the full blog text — no character truncation.
    Falls back to a truncated version only if the blog exceeds 100k chars
    (which would be an unusually large document).
    """
    # Safety cap at 100k chars (~15k words) — well beyond any normal blog
    safe_blog = blog_post[:100_000]

    key_stats = "\n".join(
        [f"- {e.snippet[:120]}... ({e.url})" for e in evidence[:5]]
    )

    response = llm.invoke([
        SystemMessage(content=CAMPAIGN_BRIEF_SYSTEM),
        HumanMessage(content=(
            f"TOPIC: {topic}\n\n"
            f"FULL BLOG POST:\n{safe_blog}\n\n"
            f"SUPPORTING EVIDENCE:\n{key_stats}"
        ))
    ])

    return response.content.strip()


def campaign_generator_node(state: State) -> dict:
    _emit(_job(state), "campaign_generator", "started", "Generating LinkedIn post and X tweet...")
    logger.info("🚀 GENERATING CAMPAIGN PACK ---")

    from Graph.templates import LINKEDIN_SYSTEM, TWITTER_TWEET_SYSTEM

    blog_post = state["final"]
    topic = state["topic"]
    evidence = state.get("evidence", [])

    # ✅ Build a full structured brief from the entire blog post.
    logger.info("📋 Building campaign brief from full blog content...")
    _emit(_job(state), "campaign_generator", "working", "Summarizing full blog for campaign brief...")

    campaign_brief = _build_campaign_brief(blog_post, topic, evidence)
    logger.info("✅ Campaign brief ready.")

    context = (
        f"TOPIC: {topic}\n\n"
        f"CAMPAIGN BRIEF (summarized from full blog):\n{campaign_brief}"
    )

    def _gen(system_prompt):
        return llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=context)
        ]).content

    with ThreadPoolExecutor(max_workers=2) as pool:
        linkedin_future = pool.submit(_gen, LINKEDIN_SYSTEM)
        twitter_future  = pool.submit(_gen, TWITTER_TWEET_SYSTEM)

    linkedin = linkedin_future.result()
    twitter  = twitter_future.result()

    logger.info("✅ LinkedIn Post and X Tweet Generated")
    _emit(_job(state), "campaign_generator", "completed", "Generated LinkedIn post and X/Twitter tweet", {"assets": 2})

    return {
        "linkedin_post":  linkedin,
        "youtube_script": "",
        "facebook_post":  "",
        "email_sequence": "",
        "twitter_thread": twitter,
        "landing_page":   "",
    }