The workflow I recommend \
This is the version I would actually build in the next 24 hours. \
🏆 FINAL ARCHITECTURE \
&#x20;                 ┌────────────────────┐ \
&#x20;                 │   CAFÉ OWNER       │ \
&#x20;                 │ Voice / Text Input  │ \
&#x20;                 └─────────┬──────────┘ \
&#x20;                           ↓ \
&#x20;                ┌─────────────────────┐ \
&#x20;                │ AGENT 1              │ \
&#x20;                │ Intent & Context     │ \
&#x20;                │ Understanding        │ \
&#x20;                └──────────┬──────────┘ \
&#x20;                           ↓ \
&#x20;                ┌─────────────────────┐ \
&#x20;                │ BUSINESS FACTS      │ \
&#x20;                │ 🔒 LOCK             │ \
&#x20;                └──────────┬──────────┘ \
&#x20;                           ↓ \
&#x20;                 OWNER CONFIRMS FACTS \
&#x20;                           ↓ \
&#x20;                ┌─────────────────────┐ \
&#x20;                │ BRAND PROFILE       │ \
&#x20;                │ + Voice + Theme     │ \
&#x20;                └──────────┬──────────┘ \
&#x20;                           ↓ \
&#x20;                ┌─────────────────────┐ \
&#x20;                │ AGENT 2             │ \
&#x20;                │ Strategy & Audience │ \
&#x20;                └──────────┬──────────┘ \
&#x20;                           ↓ \
&#x20;               ┌───────────┼───────────┐ \
&#x20;               ↓           ↓           ↓ \
&#x20;          Audience A   Audience B   Audience C \
&#x20;               ↓           ↓           ↓ \
&#x20;               └───────────┼───────────┘ \
&#x20;                           ↓ \
&#x20;                ┌─────────────────────┐ \
&#x20;                │ LOCALIZATION        │ \
&#x20;                │ + Language          │ \
&#x20;                │ + Cultural Tone     │ \
&#x20;                └──────────┬──────────┘ \
&#x20;                           ↓ \
&#x20;                ┌─────────────────────┐ \
&#x20;                │ AGENT 3             │ \
&#x20;                │ Content & Creative  │ \
&#x20;                └──────────┬──────────┘ \
&#x20;                           ↓ \
&#x20;       ┌──────────────┬────┴──────┬─────────────┐ \
&#x20;       ↓              ↓           ↓             ↓ \
&#x20;    Instagram      WhatsApp    Facebook       Poster \
&#x20;       ↓              ↓           ↓             ↓ \
&#x20;       └──────────────┴────┬──────┴─────────────┘ \
&#x20;                            ↓ \
&#x20;                  OPTIONAL SHORT VIDEO \
&#x20;                            ↓ \
&#x20;                ┌─────────────────────┐ \
&#x20;                │ PERFORMANCE AGENT   │ \
&#x20;                │ Evaluate + Score    │ \
&#x20;                └──────────┬──────────┘ \
&#x20;                           ↓ \
&#x20;                ┌─────────────────────┐ \
&#x20;                │ AUTONOMOUS          │ \
&#x20;                │ OPTIMIZER           │ \
&#x20;                └──────────┬──────────┘ \
&#x20;                           ↓ \
&#x20;                    BETTER VARIANT \
&#x20;                           ↓ \
&#x20;                ┌─────────────────────┐ \
&#x20;                │ 🔒 INTENT GUARDIAN  │ \
&#x20;                │ Facts / Claims /    │ \
&#x20;                │ Consistency Check   │ \
&#x20;                └──────────┬──────────┘ \
&#x20;                      ┌────┴────┐ \
&#x20;                      ↓         ↓ \
&#x20;                    PASS      FAIL \
&#x20;                      ↓         ↓ \
&#x20;                OWNER APPROVE  REGENERATE \
&#x20;                      ↓ \
&#x20;                FINAL CAMPAIGN \
&#x20;\
That is the architecture I would pitch. \
4\. Every step explained \
STEP 1 — Café owner login \
What it does \
Owner enters the dashboard. \
Don't overbuild this. \
For a 24-hour hackathon, use: \
Demo Café \
demo\@example.com \
&#x20;\
and maybe one simple login. \
Why? \
Authentication has almost zero hackathon-winning value. \
Spend 15–30 minutes maximum on it. \
STEP 2 — Voice or text campaign input \
This should be the first impressive interaction. \
Owner says: \
“I run a café in Bengaluru. This weekend I want to give 20 percent off coffee to college students. Make it Kannada-English and promote it on Instagram and WhatsApp.” \
&#x20;\
System converts speech to text. \
Then Agent 1 processes it. \
The track explicitly permits voice interfaces, and Agnes 3.0 Flash requires a separate speech component because it does not take audio directly.     HR26_Problem_Statements_Agnes     HR26_Problem_Statements_Agnes \
STEP 3 — Agent 1: Intent understanding \
Agent 1 should not create the campaign yet. \
Its job is: \
Understand. \
Output structured JSON: \
{ \
&#x20; "business": "Cafe XYZ", \
&#x20; "location": "Bengaluru", \
&#x20; "offer": { \
&#x20;   "discount": "20%", \
&#x20;   "product": "Coffee" \
&#x20; }, \
&#x20; "validity": "Saturday-Sunday", \
&#x20; "target_audience": ["College Students"], \
&#x20; "languages": ["English", "Kannada"], \
&#x20; "channels": ["Instagram", "WhatsApp"], \
&#x20; "tone": "Casual" \
} \
&#x20;\
Now you have something deterministic. \
STEP 4 — 🔒 Business Facts Lock \
This is one of your most important components. \
Show the owner: \
&#x20;        CAMPAIGN FACTS \
&#x20;\
Offer            20% OFF        🔒 \
Product          Coffee         🔒 \
Location         Bengaluru      🔒 \
Validity         Sat–Sun        🔒 \
Audience         Students       🔒 \
Language         Kannada/English \
&#x20;\
Owner can edit. \
Example: \
Actually make it 15%. \
&#x20;\
Now update: \
15% 🔒 \
&#x20;\
After approval, these values become locked. \
STEP 5 — Human approval \
This is where your existing point #4 belongs. \
Owner clicks: \
Approve Campaign Facts \
Now the agent gets autonomy. \
This creates a powerful boundary: \
Human controls truth. \
AI controls execution. \
That's a much better story than "AI does everything." \
STEP 6 — Brand profile \
Before generation: \
BRAND KIT \
&#x20;\
Logo \
Colors \
Tone \
Theme \
Tagline \
Visual style \
Language preference \
Forbidden claims \
&#x20;\
Example: \
Tone: Friendly \
Theme: Warm / premium \
Colors: Brown + Cream \
Language: Kannada + English \
&#x20;\
STEP 7 — Agent 2: Campaign strategy generator \
Now the AI thinks strategically. \
It determines: \
Campaign goal \
Audience strategy \
Message hierarchy \
CTA \
Channel strategy \
Content angle \
Creative direction \
&#x20;\
For example: \
Students \
Hook: affordability \
Tone: energetic \
CTA: Visit this weekend \
Young professionals \
Hook: premium coffee experience + value \
Tone: sophisticated \
Families \
Hook: weekend experience \
Tone: warm \
The brief specifically requires adaptation across audiences and channels, so this is a core component, not decoration.     HR26_Problem_Statements_Agnes \
STEP 8 — Audience segmentation \
Agent automatically creates segments. \
Example: \
Segment 1 \
College Students \
18–24 \
&#x20;\
Segment 2 \
Young Professionals \
22–35 \
&#x20;\
Segment 3 \
Families \
25–45 \
&#x20;\
Each segment gets: \
\- motivation \
\- pain point \
\- tone \
\- preferred channel \
\- messaging angle \
STEP 9 — Audience-specific messaging \
This is important. \
Don't simply create: \
Same caption translated 3 times. \
&#x20;\
Instead: \
Student \
“Weekend plans? Your coffee just got 20% cheaper.” \
&#x20;\
Young professional \
“Your weekend coffee ritual, now at 20% off.” \
&#x20;\
Family \
“Make your weekend coffee stop a little more rewarding.” \
&#x20;\
Same business offer. \
Different messaging strategy. \
STEP 10 — Localization Agent \
Now produce: \
English \
Kannada \
Kannada-English \
The localization agent should preserve: \
Offer facts \
\+ \
Intent \
&#x20;\
while changing: \
Tone \
Phrase structure \
Expressions \
CTA \
Cultural style \
&#x20;\
STEP 11 — Channel adaptation \
Now turn the strategy into channel-specific content. \
Instagram \
Hook \
Caption \
CTA \
Hashtags \
Image \
&#x20;\
WhatsApp \
Short conversational message \
CTA \
Optional image \
&#x20;\
Facebook \
Longer explanation \
CTA \
Image \
&#x20;\
This satisfies the core multi-channel requirement.     HR26_Problem_Statements_Agnes \
STEP 12 — Agent 3: Creative generation \
This should generate: \
Poster \
Instagram visual \
Story \
Optional short video \
Agnes Image 2.5 Flash is explicitly mapped to posters and social creatives, while Agnes Video can generate short 4–12 second promotional clips.     HR26_Problem_Statements_Agnes \
STEP 13 — Brand-aware generation \
Your system should pass: \
Logo \
Color palette \
Theme \
Tone \
Product image \
&#x20;\
to the creative model. \
Then output: \
Brand-consistent creative \
&#x20;\
instead of generic AI artwork. \
STEP 14 — Automatic aspect ratios \
This is a good feature, but don't waste AI calls on it. \
Use deterministic transformations. \
Example: \
Instagram Post \
1080 × 1080 \
&#x20;\
Instagram Story \
1080 × 1920 \
&#x20;\
Facebook \
1200 × 630 \
&#x20;\
The AI creates the creative once; your system adapts the layout. \
STEP 15 — Performance Intelligence ⭐ \
This should be your advanced layer. \
Don't tell judges: \
"AI knows the exact future CTR." \
&#x20;\
You cannot credibly prove that in a hackathon. \
Instead: \
Campaign Effectiveness Score \
Audience Fit          91 \
Offer Clarity         96 \
CTA Strength          84 \
Channel Fit           90 \
Localization          93 \
Brand Fit             88 \
&#x20;\
Overall               90/100 \
&#x20;\
Agnes 3.0 Flash is explicitly mapped in the brief to performance prediction and optimization.     HR26_Problem_Statements_Agnes \
STEP 16 — AI critic \
Now the model explains: \
❌ CTA is weak. \
&#x20;\
⚠️ Opening is generic. \
&#x20;\
⚠️ The visual does not emphasize the offer enough. \
&#x20;\
That produces actionable optimization instructions. \
STEP 17 — Autonomous optimizer \
Now the important part. \
Your system automatically says: \
Variant A \
Score: 76 \
&#x20;\
Problems: \
Weak hook \
Weak CTA \
&#x20;\
&#x20;       ↓ \
&#x20;\
OPTIMIZATION \
&#x20;\
Changed: \
Hook \
CTA \
Offer prominence \
&#x20;\
&#x20;       ↓ \
&#x20;\
Variant B \
Score: 89 \
&#x20;\
That is the part judges can clearly recognize as agentic behavior. \
STEP 18 — 🔒 Intent Guardian \
Now verify every output. \
For example: \
ORIGINAL FACTS \
&#x20;\
20% OFF \
Coffee \
Saturday–Sunday \
Bengaluru \
&#x20;\
Generated content: \
20% OFF              ✅ \
Coffee               ✅ \
Saturday–Sunday      ✅ \
Bengaluru            ✅ \
&#x20;\
Then check: \
Unsupported claims \
"Best coffee in Bengaluru" \
&#x20;\
Owner never said that. \
System: \
⚠️ Unsupported claim detected. \
&#x20;\
Conflict \
20% → 25% \
&#x20;\
System: \
🚨 OFFER CONFLICT — BLOCKED \
&#x20;\
This can become your strongest technical differentiator. \
STEP 19 — Human approval \
Only after: \
generation → optimization → verification \
does the owner approve the final campaign. \
This is better than your original flow. \
Final flow: \
AI creates \
↓ \
AI optimizes \
↓ \
AI verifies \
↓ \
Human approves \
STEP 20 — Campaign version history \
Store: \
v1 \
v2 \
v3 \
&#x20;\
Show: \
v3 changed tone and headline. \
&#x20;\
Offer remained unchanged. \
&#x20;\
This is directly useful because the problem says requirements can change while approved information should not be lost.     HR26_Problem_Statements_Agnes \
5\. The most important advanced feature \
You marked: \
⭐ Performance Intelligence \
&#x20;\
I'd actually upgrade that into: \
🏆 Self-Optimizing + Intent-Locked Campaign Engine \
Because performance intelligence alone is not enough. \
Your winning loop should be: \
USER INPUT \
&#x20;  ↓ \
UNDERSTAND \
&#x20;  ↓ \
LOCK FACTS \
&#x20;  ↓ \
PLAN \
&#x20;  ↓ \
GENERATE \
&#x20;  ↓ \
SCORE \
&#x20;  ↓ \
CRITIQUE \
&#x20;  ↓ \
OPTIMIZE \
&#x20;  ↓ \
VERIFY AGAINST LOCKED FACTS \
&#x20;  ↓ \
HUMAN APPROVAL \
&#x20;\
This directly covers the three mandatory objectives in one coherent system.     HR26_Problem_Statements_Agnes \
6\. A killer feature you haven't written in the notebook \
Add this: \
🔥 "Change Anything — Protect What Matters" \
This could win your demo. \
Start with: \
20% OFF \
Coffee \
Saturday-Sunday \
Students \
Kannada + English \
&#x20;\
Generate the campaign. \
Then tell the system: \
“Change the target audience to families and make the campaign premium.” \
&#x20;\
The system changes: \
✅ Audience messaging \
✅ Tone \
✅ Visual style \
✅ Headline \
✅ CTA   \
But: \
🔒 20% stays 20% \
🔒 Coffee stays Coffee \
🔒 Saturday–Sunday stays Saturday–Sunday \
Dashboard: \
&#x20;            CAMPAIGN UPDATE \
&#x20;\
Audience              🔄 Changed \
Tone                  🔄 Changed \
Visual                🔄 Changed \
CTA                   🔄 Changed \
&#x20;\
Offer                 🔒 Preserved \
Product               🔒 Preserved \
Dates                 🔒 Preserved \
Location              🔒 Preserved \
&#x20;\
Intent Integrity: 100% ✅ \
&#x20;\
That is a very strong demonstration of the actual problem. \
7\. What should be Agent vs deterministic code? \
This matters a lot. \
Don't make everything an LLM. \
Agent 1 — AI \
Intent understanding \
Missing information detection \
Clarification questions \
Agent 2 — AI \
Campaign strategy \
Audience segmentation \
Messaging strategy \
Localization \
Agent 3 — AI \
Copy \
Creative direction \
Image generation \
Video prompt \
Performance Agent — AI + rules \
Campaign critique \
Performance scoring \
Optimization suggestions \
Intent Guardian — mostly deterministic \
Use Python/Pydantic/rules for: \
Discount \
Dates \
Product \
Location \
Required phrases \
Restricted claims \
This makes your system much more trustworthy. \
8\. Database structure \
You don't need a huge database. \
Use around these tables: \
users \
business_profiles \
brand_kits \
campaigns \
campaign_facts \
audiences \
campaign_variants \
campaign_assets \
performance_scores \
campaign_versions \
approvals \
&#x20;\
Most important: \
campaign_facts \
campaign_id \
field \
value \
locked \
approved_at \
&#x20;\
campaign_versions \
campaign_id \
version \
changes \
created_at \
&#x20;\
performance_scores \
variant_id \
audience_fit \
offer_clarity \
cta_strength \
channel_fit \
localization \
overall_score \
&#x20;\
9\. API workflow \
Your FastAPI backend can roughly have: \
POST /campaign/create \
POST /campaign/extract-intent \
POST /campaign/approve-facts \
&#x20;\
POST /campaign/strategy \
POST /campaign/segments \
POST /campaign/localize \
&#x20;\
POST /campaign/generate-copy \
POST /campaign/generate-image \
POST /campaign/generate-video \
&#x20;\
POST /campaign/evaluate \
POST /campaign/optimize \
POST /campaign/verify \
&#x20;\
POST /campaign/approve \
GET  /campaign/{id} \
GET  /campaign/{id}/versions \
&#x20;\
Don't create actual microservices. \
One FastAPI application is enough. \
10\. Your frontend should look like this \
Don't create 20 pages. \
Page 1 — Dashboard \
My Campaigns \
\+ Create Campaign \
&#x20;\
Page 2 — Campaign creation \
Large: \
🎤 Speak your campaign \
or \
⌨️ Type your idea \
Page 3 — Intent confirmation \
Campaign Facts 🔒 \
&#x20;\
Page 4 — Strategy \
Audience \
Channels \
Languages \
Tone \
&#x20;\
Page 5 — Generated campaign \
Tabs: \
Instagram | WhatsApp | Facebook | Creative \
Page 6 — Performance \
Variant A: 76 \
Variant B: 89 \
Variant C: 81 \
&#x20;\
AI Recommendation: B \
&#x20;\
Page 7 — Verification \
Intent Integrity ✅ \
Offer Integrity ✅ \
Brand Integrity ✅ \
Localization ✅ \
&#x20;\
Page 8 — Final approval \
Approve Campaign \
11\. What to build in the next 24 hours \
This is where you need discipline. \
Hours 0–3 \
Build: \
Next.js frontend \
FastAPI backend \
Agnes API integration \
Basic campaign schema \
Hours 3–6 \
Build: \
Voice/text input \
Agent 1 \
Intent extraction \
Facts editor \
Facts lock \
This is your foundation. \
Hours 6–10 \
Build: \
Agent 2 \
Audience segmentation \
Campaign strategy \
Localization \
Multi-channel messaging \
Hours 10–14 \
Build: \
Agent 3 \
Instagram \
WhatsApp \
Facebook \
Image generation \
Brand assets \
Hours 14–17 \
Build: \
Performance scoring \
AI critic \
Autonomous optimization \
Hours 17–20 \
Build: \
Intent Guardian \
Claim detection \
Version history \
Approval flow \
Hours 20–22 \
Build: \
Premium UI \
Loading states \
Error handling \
Demo fallback assets \
Hours 22–24 \
Do not add new major features. \
Use the time for: \
testing \
demo rehearsal \
bug fixing \
pitch \
screenshots/video \
backup plan \
12\. What I would cut from your original drawing \
Keep \
✅ Login \
✅ Voice/text \
✅ Edit details \
✅ Human approval \
✅ Tone/theme \
✅ Strategy generator \
✅ Audience segmentation \
✅ Audience-specific messaging \
✅ Instagram \
✅ WhatsApp \
✅ Facebook \
✅ Poster \
✅ Short video \
✅ Brand assets \
✅ Aspect ratio \
✅ Performance intelligence   \
Change \
"Language conversion" \
→ Localization Agent \
"Manual approve details" \
→ Approve locked business facts \
"Performance intelligence" \
→ Performance → Critique → Optimize loop \
Add \
🔥 Business Facts Lock \
🔥 Intent Guardian \
🔥 Unsupported Claim Detector \
🔥 Campaign Versioning \
🔥 Change Request Engine \
🔥 Human Approval after verification \
Those six additions are what turn your drawing from “AI generates campaigns” into a credible agentic marketing system. \
Final workflow you should draw on the whiteboard \
&#x20;         🎤 VOICE / TEXT \
&#x20;               ↓ \
&#x20;       AGENT 1: UNDERSTAND \
&#x20;               ↓ \
&#x20;      🔒 BUSINESS FACTS \
&#x20;               ↓ \
&#x20;         HUMAN CONFIRM \
&#x20;               ↓ \
&#x20;          BRAND KIT \
&#x20;               ↓ \
&#x20;      AGENT 2: STRATEGY \
&#x20;               ↓ \
&#x20;       AUDIENCE SEGMENT \
&#x20;               ↓ \
&#x20;         LOCALIZATION \
&#x20;               ↓ \
&#x20;      CHANNEL ADAPTATION \
&#x20;               ↓ \
&#x20;      AGENT 3: GENERATION \
&#x20;         ↙      ↓      ↘ \
&#x20;    COPY      IMAGE    VIDEO \
&#x20;         ↘      ↓      ↙ \
&#x20;         PERFORMANCE \
&#x20;            INTELLIGENCE \
&#x20;               ↓ \
&#x20;           AI CRITIC \
&#x20;               ↓ \
&#x20;       AUTONOMOUS OPTIMIZER \
&#x20;               ↓ \
&#x20;         NEW VARIANT \
&#x20;               ↓ \
&#x20;       🔒 INTENT GUARDIAN \
&#x20;          ↙          ↘ \
&#x20;       PASS          FAIL \
&#x20;        ↓              ↓ \
&#x20;     APPROVE       REGENERATE \
&#x20;        ↓ \
&#x20;    FINAL CAMPAIGN \
&#x20;        ↓ \
&#x20;   VERSION + EXPORT \
&#x20;\
That is the version I would build. \
One more constraint: the Agnes brief says video is asynchronous and limited to 1 RPM, so video should be an optional layer rather than something your core workflow depends on. Keep a pre-generated fallback clip for the demo.     HR26_Problem_Statements_Agnes     HR26_Problem_Statements_Agnes \
The single most important engineering decision is this: lock the business facts before giving the agents autonomy, then force every optimized output through the Intent Guardian. That is the piece I'd make the judges remember.