# **Strategic Architecture and Implementation Blueprint for an Academic AI Agent in the Nigerian Context**

The deployment of a WhatsApp-based artificial intelligence agent for the retrieval and ingestion of academic past papers presents a unique intersection of infrastructural, economic, and socio-technical challenges. Designed as a community resource—and specifically as a *sadaqah jariyah* (continuous charity) for the Pan-Atlantic University (PAU) Muslim Students' Association (MSA)—this system must navigate the constraints of intermittent power, high-latency networks, limited operational budgets, and the sociological dynamics of crowdsourced content. Furthermore, the operational reality of a solo developer building the system in weekend increments necessitates a profound bias toward operational simplicity, serverless architectures, and managed services.

This exhaustive report provides a granular analysis of the architectural, infrastructural, and strategic paradigms required to construct, scale, and sustain this system. It strictly adheres to the locked technology stack—utilizing Gemini 3.1 Pro Preview and Gemini 3 Flash for cognitive reasoning and multimodal optical character recognition (OCR), Cloud SQL PostgreSQL with pgvector for state and semantic retrieval, Cloud Run for zero-scaled compute, and the WhatsApp messaging ecosystem. The analysis is divided into seven critical domains, evaluating the current state of the art in early 2026, comparing specific tools, identifying severe failure modes, and prescribing concrete recommendations optimized for the Lagos development context.

## **Area 1: Existing Past Paper Bank Tools in African University Contexts**

The landscape of academic repositories in African universities is heavily fragmented, bridging the gap between highly structured global software-as-a-service (SaaS) platforms and highly informal, ad-hoc local networks. Understanding the structural successes and failures of these existing paradigms is crucial for designing a resilient V1 architecture.

### **Current State of the Art (Late 2025 / Early 2026\)**

The current state of the art for academic material distribution in Nigerian universities remains heavily localized to WhatsApp group chats and scattered Google Drive repositories. While global platforms have pioneered advanced OCR, flashcard generation, and AI-driven tutoring, these features rarely penetrate the African market effectively due to paywalls and a lack of hyper-local, institution-specific content. The technological frontier is currently moving toward conversational interfaces, where students interact with institutional knowledge bases via messaging applications they already use daily, minimizing the friction of downloading separate applications or navigating complex web portals.

### **Tool and Platform Comparison**

| Platform Category | Specific Examples | Technical & Operational Specifications |
| :---- | :---- | :---- |
| **Global SaaS Repositories** | StuDocu, Course Hero, Pastest | Highly structured databases with advanced gamification and subscription paywalls. They rely on massive user bases to generate network effects. Pricing typically ranges from $10 to $30 monthly, which presents a significant barrier in the Nigerian economic context. |
| **Emerging African Platforms** | MyExams.ng, ExamPro | Web-based portals attempting to localize the Course Hero model for Nigerian institutions like UNILAG, OAU, and PAU. They often struggle with content acquisition and suffer from high churn rates due to incomplete databases and poor mobile-web optimization on low-end Android devices. |
| **Informal Ad-Hoc Networks** | Departmental WhatsApp Groups, MSA Google Drives | Completely free and heavily utilized. However, they lack semantic search capabilities. A student looking for a 2023 Principles of Economics paper must manually scroll through months of chat history or navigate poorly organized folder hierarchies. |

### **Failure Modes and Gotchas**

The overwhelming vulnerability of any digital repository is the "cold start" or bootstrap problem. Research into organizational ecosystems indicates that digital commons frequently collapse due to an unsustainable contribution-to-consumption ratio.1 The established heuristic in digital communities—the 1% rule, where 1% of users create, 9% curate, and 90% passively consume—is often exacerbated in high-stress academic environments.

Past paper banks specifically die within the first sixty days when passive consumers abandon the platform due to an empty or irrelevant corpus. Once the consumers leave, the few active contributors lose the social incentive or intrinsic motivation to continue digitizing their physical materials.1 Furthermore, unstructured WhatsApp groups fail at scale because media files are frequently purged from device storage to save space, and Google Drives degrade into digital dumping grounds lacking standardized naming conventions.

### **Recommendations for the PAU MSA Scope**

For a solo developer operating within weekend chunks, the system must not attempt to emulate the complex gamification or subscription models of Course Hero. The recommendation is to strictly bridge the gap between the informal WhatsApp group and the structured database. By utilizing WhatsApp as the interface and a structured Postgres database as the backend, the system meets the students where they are. The architecture must prioritize retrieval speed and accuracy over complex community features, ensuring that the 90% of users who act as passive consumers immediately find value, thereby sustaining the platform's reputation and encouraging the 1% to continue contributing.

## **Area 2: WhatsApp Infrastructure for African Deployment**

Developing a WhatsApp-native application in 2026 requires navigating Meta’s evolving pricing architecture and the complex ecosystem of Business Solution Providers (BSPs). The selection of the routing infrastructure directly dictates the financial viability of a system operating on a restricted \~$1000 Google Cloud Platform (GCP) credit budget.

### **Current State of the Art (Late 2025 / Early 2026\)**

Effective July 2025, Meta transitioned the WhatsApp Business API from a conversation-based pricing model to a per-message billing system for business-initiated templates.3 This granular model categorizes messages into four distinct types: Marketing, Utility, Authentication, and Service.3

For an academic agent queried by students, the "Service" category is the absolute focal point. When a user initiates a message (e.g., sending a photograph of a past paper or requesting a document), a 24-hour customer service window opens.3 Crucially, any free-form message sent by the business within this 24-hour window is completely free from Meta's side.4 Because the PAU MSA agent operates purely on a request-response mechanism initiated by the students, Meta’s base API fees effectively approach zero. The infrastructure cost is therefore entirely dictated by the chosen BSP's markup and server costs.

### **Infrastructure Provider Comparison**

| Provider | Pricing and Markup | Verification & Developer Experience | African Context Reliability |
| :---- | :---- | :---- | :---- |
| **Twilio for WhatsApp** | $0.005 per message (inbound and outbound) \+ Meta fees.6 Platform fee is $0 (Pay-as-you-go).7 | Exceptional documentation. Sandbox allows instant deployment without Meta verification.7 | Highly reliable global infrastructure, though lacks specific Nigerian Do-Not-Disturb (DND) bypass routing (which is mostly irrelevant for WhatsApp). |
| **Meta Cloud API (Direct)** | $0.00 markup. Only raw Meta fees apply. | Highest maintenance. Requires managing authentication tokens, webhooks, and raw JSON payloads. Verification takes 1-6 weeks.8 | Highly cost-effective but demands significant developer overhead and raw infrastructural management. |
| **Termii** | \~$0.0107 per message (varies by volume).7 | Purpose-built for verification and transactional messaging in Nigeria.7 | Deeply integrated into the Nigerian telecom ecosystem, excelling at SMS DND bypass, but less optimized for rich-media WhatsApp conversational agents.7 |
| **Sendchamp** | Custom local pricing, pay-as-you-go.7 | No-code setup for non-technical teams.7 | Offers unified omnichannel routing and local currency support, but ecosystem and documentation are still maturing compared to global leaders.7 |
| **Africa's Talking** | Varies by volume, highly competitive for SMS.7 | Excellent sandbox and local developer support.10 | Deep Pan-African penetration. Exceptional for USSD and SMS, but their WhatsApp API pricing remains equivalent to standard BSP markups.7 |

### **Failure Modes and Gotchas**

The most severe friction point for a Lagos-based developer is Meta's Business Verification process. Rejections are overwhelmingly caused by legal versus trade name mismatches.11 Meta's automated systems and manual reviewers require that the exact legal entity name (e.g., as registered with the Corporate Affairs Commission in Nigeria) be reflected perfectly on the supporting website's footer, privacy policy, and domain email.11 Providing a casual trade name while submitting official legal documents will trigger infinite rejection loops.

Additionally, the phone number utilized must be entirely clean and disconnected from any consumer WhatsApp application.8 Attempting to migrate an active personal or standard WhatsApp Business App number to the API without properly deleting the consumer account first will result in total routing failures.

### **Recommendations for the PAU MSA Scope**

For a solo developer operating in 12-16 hour weekend chunks, time-to-first-message is the paramount metric. The recommendation is to utilize **Twilio for WhatsApp**.

The cheapest path to a working number that can handle inbound image attachments begins with the Twilio Sandbox. The Sandbox requires zero verification and zero upfront cost, allowing the developer to build and test the entire webhook-to-Cloud-Run pipeline within the first weekend. Time-to-first-message from zero is under an hour.

Regarding monthly costs at under 1000 messages: because the agent relies on user-initiated Service conversations, Meta's fees are zero. Twilio's $0.005 flat rate applies to both the inbound query and the outbound response.6 Thus, one complete interaction costs $0.01. At 1000 complete interactions (2000 messages), the monthly cost is a highly sustainable $10.00.

When scaling to 5000-10000 messages, the cost rises linearly to $50-$100 per month. At this scale, the primary breaking point will not be WhatsApp routing, but rather Cloud Run cold starts and webhook timeout limits. Twilio enforces a strict 15-second timeout on webhooks; because Gemini OCR can take longer, the architecture must instantly return a 200 OK to Twilio upon receiving the image, enqueue the OCR task asynchronously (e.g., via Google Cloud Tasks), and push the final response back to the user via the Twilio API once processing is complete.

## **Area 3: Gemini 3.1 Pro Preview \+ Flash for Academic OCR**

The ingestion of academic materials via mobile photography in Nigerian university classrooms involves severe visual distortions. Students utilize cheap Android devices, capturing documents under fluorescent glare, at skewed angles, and frequently featuring complex mixed-script content, particularly Arabic and Latin scripts common in Islamic Studies courses at the PAU MSA.

### **Current State of the Art (Late 2025 / Early 2026\)**

Released as Google's frontier reasoning model, Gemini 3.1 Pro Preview features a 1 million token context window and exhibits unprecedented depth in multimodal tasks.13 The paradigm has shifted from dedicated OCR pipelines (like Tesseract) to large multimodal models (LMMs) that perform OCR inherently while structuring the output into semantic JSON objects.

### **Tool Comparison and Benchmarks**

Early 2026 benchmarks demonstrate Gemini 3.1 Pro Preview's superiority in academic reasoning and multimodal understanding compared to its contemporaries:

| Model | Humanity's Last Exam (Text \+ Vision) | ARC-AGI-2 (Abstract Reasoning) | Pricing (Input / Output per 1M tokens) |
| :---- | :---- | :---- | :---- |
| **Gemini 3.1 Pro Preview** | 44.4% 13 | 77.1% 14 | $2.00 / $12.00 15 |
| **Claude 4.6 Sonnet** | 33.2% 14 | 58.3% 14 | Comparatively higher |
| **GPT-5.2 (High)** | 34.5% 14 | 52.9% 14 | $1.75 / $14.00 (Codex variant) 17 |

Crucially for the MSA context, Gemini 3.1 Pro Preview is recognized as the industry leader for Arabic language reasoning and mixed-script comprehension.18 It effortlessly manages the right-to-left optical character recognition alongside left-to-right English text within the same spatial boundaries, a task where traditional OCR engines frequently fail.

### **Failure Modes and Pre-Processing Gotchas**

While Gemini 3.1 Pro Preview is highly resilient, submitting raw, low-quality photos directly to the model increases hallucination rates and wastes tokens. At what photo quality does the cheaper Gemini 3 Flash start failing? Flash is sufficient for clean, perfectly lit scans or digital PDFs. However, the moment a photo exhibits glare masking text, geometric skew exceeding 10 degrees, or complex mathematical formulas, Flash's attention mechanism degrades, leading to skipped lines or misclassified characters.

Pre-processing is therefore mandatory to normalize the image before payload transmission. Utilizing Python and OpenCV on Cloud Run, the pipeline should execute the following operations:

1. **Deskewing:** Utilizing cv2.findContours and cv2.minAreaRect to detect the dominant text angle and applying an affine transformation to correct rotational skew.19  
2. **Adaptive Thresholding:** Replacing global thresholding with cv2.adaptiveThreshold to resolve uneven shadows cast by mobile phones over the document.20 Adaptive thresholding computes the threshold for small regions of the image, making it highly robust against localized classroom glare.20  
3. **Contrast Limited Adaptive Histogram Equalization (CLAHE):** Applied to boost faded ink or low-quality photocopies without destroying thin academic tables or diagrams.21

### **Recommendations for the PAU MSA Scope**

The routing logic must be bifurcated to optimize the \~$1000 GCP credits. Gemini 3 Flash should be utilized strictly for conversational routing, intent detection, and generating empathetic responses to user queries. If a user uploads an image, Flash should rapidly classify it (e.g., "Is this an exam paper or a casual photo?"). Once classified as academic, the payload is handed to Gemini 3.1 Pro Preview for heavy extraction into a structured JSON format (Course Code, Year, Semester, Question Array).

Regarding cost projections on Vertex AI: A standard 2K resolution image consumes exactly 1120 tokens, resulting in a base cost of approximately $0.134 per image via the standard API.22 Processing 500 high-complexity past paper photos a month equates to a predictable $67.00 monthly expenditure. For non-urgent processing, Vertex AI's Batch API slashes this cost by 50% ($0.067 per image).22 A solo developer should implement an asynchronous queueing system where user-uploaded papers are placed in a GCP Pub/Sub queue, processed in batches during off-peak hours to stretch the credit budget, and the user is notified via WhatsApp when their uploaded paper has been successfully indexed.

## **Area 4: pgvector on Cloud SQL Postgres for Academic Content Retrieval**

Extracting text via Gemini is only the ingestion phase; retrieving the exact past paper based on a colloquial WhatsApp query (e.g., "Do you have the midterm questions for Principles of Economics from last year?") requires an advanced search architecture. The pgvector extension transforms Cloud SQL Postgres into a highly capable, transactional retrieval engine, eliminating the need to manage a separate standalone vector database.23

### **Current State of the Art (Late 2025 / Early 2026\)**

The modern paradigm for Retrieval-Augmented Generation (RAG) avoids pure semantic search in favor of Hybrid Search. Vector search solves the semantic understanding problem (knowing that "macroeconomics" and "GDP" are related), but BM25 lexical search provides the exact-match precision required for course codes (e.g., "ECO201" vs "ECO202").25

### **Tool Comparison and Granularity**

When designing the database schema, the granularity of the embeddings is the most critical architectural decision.

1. **Paper-Level Embedding:** Embedding an entire 5-page exam as a single vector results in severe semantic dilution. A highly specific question on Islamic jurisprudence gets lost in the multidimensional noise of the broader document.  
2. **Course-Level Embedding:** Far too broad, resulting in the retrieval of hundreds of irrelevant questions.  
3. **Question-Level Embedding (Recommended):** The optimal approach is a hierarchical schema. Documents are parsed and stored at the paper level with strict relational metadata. The text is then chunked at the *question or thematic section level*, with each chunk embedded as a distinct vector that retains a foreign key linking back to the parent paper.25

For the embedding model choice, open-source alternatives (like sentence-transformers) offer free inference but require dedicated compute instances, which violates the scale-to-zero serverless architecture required by the budget. Google's text-embedding-004 (or equivalent Vertex AI text-embedding models) should be utilized. It provides high-quality 768-dimensional embeddings via an API call, seamlessly covered by the existing GCP credit pool without adding infrastructure overhead.

### **Hybrid Search and Schema Design**

To merge the semantic understanding of pgvector with the lexical precision of PostgreSQL's full-text search, the system must utilize Reciprocal Rank Fusion (RRF). RRF mitigates score scaling issues by ranking documents based on their position in each respective list using the mathematical formula: ![][image1] (where ![][image2] is traditionally set to 60).27

The schema design must support aggressive pre-filtering before the vector distance calculations to ensure sub-millisecond query performance 30:

SQL

CREATE TABLE past\_papers (  
    paper\_id SERIAL PRIMARY KEY,  
    course\_code VARCHAR(10) NOT NULL,  
    exam\_year INT,  
    semester VARCHAR(20),  
    exam\_type VARCHAR(50), \-- e.g., 'Midterm', 'Final', 'CA'  
    raw\_pdf\_url TEXT  
);

CREATE TABLE paper\_questions (  
    question\_id SERIAL PRIMARY KEY,  
    paper\_id INT REFERENCES past\_papers(paper\_id),  
    question\_text TEXT,  
    embedding VECTOR(768) \-- Matches Vertex AI embedding dimensions  
);

\-- B-Tree Index for exact match filtering  
CREATE INDEX idx\_course\_code ON past\_papers(course\_code);

### **Indexing Strategies and Failure Modes**

At a small scale of 500 to 2000 embedded papers (resulting in roughly 10,000 to 50,000 question-level vectors), the choice of vector index dictates performance.30 pgvector offers IVFFlat and HNSW (Hierarchical Navigable Small World) indexes.23

The primary failure mode is utilizing IVFFlat for small, rapidly growing datasets. IVFFlat requires a training step (calculating k-means centroids) only after the table has sufficient data 32; if built too early, recall drops drastically. The recommendation is to utilize HNSW. While it consumes marginally more memory and takes slightly longer to build than IVFFlat, HNSW provides exceptionally high recall without the requirement of a training step, executing sub-20ms queries for datasets up to 1 million vectors.23

At the projected scale of 500-2000 students generating read-heavy traffic, a single db-f1-micro Cloud SQL instance is more than sufficient. The relational SQL queries filter by course\_code via standard B-tree indexes, drastically reducing the vector search space before pgvector calculates the cosine distance, ensuring immediate query execution.23

## **Area 5: User Onboarding and Persistent Memory for Community-Scale Agents**

Designing a WhatsApp agent for 500-2000 students necessitates a memory architecture that balances deep personalization with strict operational efficiency. If the agent greets a new user with a rigid, multi-step questionnaire ("Please enter your Level," "Please enter your Major"), it mimics a bureaucratic form, creating immediate user friction and abandonment.

### **Current State of the Art (Late 2025 / Early 2026\)**

The paradigm for onboarding in conversational AI has shifted from explicit form-filling to implicit data extraction. Systems like Folk by Nozomio (a consumer personal AI) pioneered the approach of separating the shared global entity network from the user's private state. In the PAU MSA context, the past papers represent the immutable global entity network, while the user's query history, academic level, and enrolled courses represent the isolated private state.

### **Onboarding Flow Design and Schema**

Onboarding should be completely implicit. The system records the user's WhatsApp phone number as the primary key upon the first interaction. When the student naturally asks for a document (e.g., "Hey, I need the 200 level accounting past questions for my CA"), Gemini 3 Flash intercepts the message and performs structured extraction. It identifies the implicit data points (Level: 200, Major/Interest: Accounting) and asynchronously triggers an UPSERT to the PostgreSQL user table.

If critical data is missing during a complex request, the agent can append a conversational prompt to its response: "Here is your accounting paper\! By the way, what specific degree are you pursuing so I can prioritize your core courses?"

The user table schema should avoid premature optimization:

SQL

CREATE TABLE users (  
    phone\_number VARCHAR(20) PRIMARY KEY,  
    name VARCHAR(100), \-- Extracted from WhatsApp profile payload  
    academic\_level INT,  
    major VARCHAR(100),  
    inferred\_courses TEXT, \-- Array of course codes updated implicitly  
    interaction\_count INT DEFAULT 0,  
    last\_active TIMESTAMP DEFAULT CURRENT\_TIMESTAMP  
);

### **Failure Modes and Log Retention**

The most common failure mode for conversational agents at a community scale is maintaining endless rows of raw message histories. Storing every message indefinitely leads to rapid database bloat, increased latency when injecting context into the LLM prompt, and introduces severe privacy liabilities.

The recommendation is to maintain a rolling "window buffer memory" of only the last 5 to 10 raw messages for immediate conversational context.33 Periodically, a lightweight cron job (managed via Google Cloud Scheduler triggering a Cloud Run endpoint) should invoke Gemini 3 Flash to read the raw logs. The LLM synthesizes a compressed JSON summary of the user's current needs and state, appends it to a dedicated user\_summaries text column in the database, and permanently truncates the raw logs. This approach ensures that the agent retains long-term memory of the student's academic journey while remaining exceptionally lightweight and compliant with data minimization principles.

## **Area 6: V1 Feature Scoping Within the Past Paper Bank**

Scope creep is the primary threat to solo development, particularly in a weekend-constrained paradigm. Evaluating the four proposed V1 feature variants reveals clear dividing lines in bootstrap difficulty, day-one utility, and maintenance burden.

### **Feature Evaluation**

1. **Pure Ingestion \+ Retrieval (Text/PDF)**  
   * *Probability of Shipping in a Weekend:* High. The pipeline (WhatsApp webhook ![][image3] Cloud Run ![][image3] Gemini OCR ![][image3] pgvector ![][image3] WhatsApp reply) is linear and deterministic.  
   * *Bootstrap Severity:* High. If the database is empty, the feature is useless.  
   * *Day-One Utility:* Massive. It solves the immediate, acute pain point of exam preparation without requiring a behavioral shift from the student.  
   * *Maintenance Burden:* Low. Once the RAG pipeline is stable, it requires minimal oversight.  
   * *V2 Implications:* Establishes the foundational database schema and vector infrastructure required for any future AI capabilities.  
2. **Ingestion \+ Retrieval \+ AI Summarization**  
   * *Probability of Shipping in a Weekend:* Medium. Summarizing academic concepts accurately without hallucinations requires extensive system prompting and higher output token expenditures.  
   * *Bootstrap Severity:* High. Still relies entirely on an existing corpus.  
   * *Day-One Utility:* Moderate. Students generally prefer to see the raw past questions to gauge formatting and examiner style before seeking synthesized summaries.  
   * *Maintenance Burden:* Medium. Requires monitoring for hallucinated facts.  
3. **Ingestion \+ Retrieval \+ Practice Mode (Quizzing)**  
   * *Probability of Shipping in a Weekend:* Low. Constructing conversational state machines capable of scoring human answers, handling multi-turn corrections, and managing edge cases in logic requires dedicated backend orchestration and complex state tracking.  
   * *Bootstrap Severity:* High.  
   * *Day-One Utility:* High, but heavily reliant on the absolute accuracy of the scoring model. A false negative (scoring a correct answer as incorrect) instantly destroys trust in the system.  
   * *Maintenance Burden:* High.  
4. **Ingestion \+ Retrieval \+ Collaborative Annotations**  
   * *Probability of Shipping in a Weekend:* Very Low. Requires building conflict resolution, user permissions, moderation queues, and complex relational mappings for multiple users interacting with a single document.  
   * *Bootstrap Severity:* Extreme. Requires not just a corpus of papers, but an active, concurrent user base to generate the annotations.  
   * *Day-One Utility:* Zero, until the network effect is achieved.

### **Recommended Sequencing**

The absolute mandate for a solo developer building a *sadaqah jariyah* project is strict adherence to **Variant 1: Pure Ingestion \+ Retrieval**. This establishes the core value proposition—a reliable, immutable archive. It is boring, highly reliable, and heavily leverages the strengths of PostgreSQL and Cloud Run.

Variant 2 (Summarization) should be targeted for V1.1, introduced as a simple conversational toggle once the V1 retrieval baseline demonstrates a 99% uptime. Variant 3 (Practice Mode) represents the ultimate trajectory for V2, transforming the platform from an archive into an active tutor. Collaborative annotations should be deferred indefinitely; WhatsApp's linear, text-based interface is fundamentally unsuited for complex, multi-user document collaboration.

## **Area 7: Content Bootstrap Strategy for the Past Paper Bank**

The fundamental vulnerability of any digital repository relies on the "cold start" or bootstrap problem. Without a critical mass of initial utility, passive consumers abandon the platform, and the few active contributors lose the incentive to digitize their materials.

### **Current State of the Art (Late 2025 / Early 2026\)**

Successfully bootstrapped communities rarely rely on organic, day-one contributions. They utilize hybrid seeding models. Launching empty and relying on organic contribution is a guaranteed failure mode, colloquially known as the "empty restaurant" effect.

### **Bootstrap Options and Evaluation**

1. **Mass-Import from Existing PAU MSA Google Drive:** This is the most critical first step. Processing the existing ad-hoc system through the Gemini OCR pipeline provides an immediate baseline of utility. It transforms the first interaction of a new user from a request for contribution into a successful retrieval event, building immediate trust.  
2. **Recruiting Seeders:** The strategy must involve recruiting 5-10 specific "seeders" (bridging actors) across different academic levels and majors prior to public deployment.1 These individuals should be incentivized (socially or otherwise) to photograph and upload their physical archives during the beta testing phase.  
3. **LLM-Assisted Knowledge Extraction:** Where definitive past papers are scarce, the system can utilize Gemini 3.1 Pro Preview to extract structurally similar questions from generic course materials. By ingesting course syllabi, lecture slides, and textbook problem sets, the LLM can generate synthetic past papers formatted precisely like real exams.

### **Failure Modes**

The primary gotcha with LLM-assisted extraction is the degradation of academic integrity. If synthetic questions are presented as actual past exam questions, and the professor deviates from that format, the students will blame the platform.

### **Recommendations for the PAU MSA Scope**

The strategy must be a **Hybrid Approach**.

First, dedicate an entire weekend strictly to mass-importing the Google Drive content before the public launch. Second, recruit the 5-10 seeders from the MSA executive committee to test the ingestion pipeline with their own physical papers.

Finally, utilize LLM-assisted extraction carefully. Extract questions from lecture slides and study guides to bootstrap a starter corpus for barren courses, but mandate that the database schema includes an is\_synthetic boolean flag. When the WhatsApp agent retrieves these questions, it must explicitly state: *"I couldn't find the exact past paper, but based on the lecture slides for this course, here are the most probable questions you will face."* This maintains total transparency, provides immense day-one utility, and circumvents the catastrophic failure mode of an empty corpus.

## **Conclusion**

The construction of an AI-powered academic agent for the PAU MSA is a highly feasible undertaking for a solo developer utilizing the specified Google Cloud Platform stack. By leveraging the recent shift in Meta's API pricing, the operational costs for a purely responsive, service-window-driven agent are virtually eliminated, isolating the primary expenditures to Twilio's routing fees, Cloud SQL uptime, and Gemini's token usage.

To ensure sustainability within the \~$1000 credit limit, the architecture must rely heavily on Cloud Run's scale-to-zero capabilities, utilize batch processing for non-urgent document ingestion, and restrict real-time processing to the highly efficient Gemini 3 Flash model, reserving Gemini 3.1 Pro Preview strictly for complex, multimodal academic OCR. By front-loading the repository with pre-existing materials to shatter the crowdsourcing bootstrap problem, utilizing Hybrid Search (BM25 \+ pgvector via RRF) to guarantee retrieval precision, and maintaining a ruthless focus on pure retrieval for the V1 release, the developer guarantees a high-impact, low-maintenance deployment. This blueprint favors operational resilience over experimental complexity, perfectly aligning with the ethos of a continuous, self-sustaining community asset.

#### **Works cited**

1. Together we create value: a study of a crowdsourcing community | Internet Research, accessed May 2, 2026, [https://www.emerald.com/intr/article/31/3/911/390531/Together-we-create-value-a-study-of-a](https://www.emerald.com/intr/article/31/3/911/390531/Together-we-create-value-a-study-of-a)  
2. Crowdsourcing Consumer Research \- Academia.edu, accessed May 2, 2026, [https://www.academia.edu/35201893/Crowdsourcing\_Consumer\_Research](https://www.academia.edu/35201893/Crowdsourcing_Consumer_Research)  
3. WhatsApp Business API Pricing: Complete Guide (2026) \- Spur, accessed May 2, 2026, [https://www.spurnow.com/en/blogs/whatsapp-business-api-pricing-explained](https://www.spurnow.com/en/blogs/whatsapp-business-api-pricing-explained)  
4. WhatsApp Business API Pricing 2026: Complete Cost Guide with Country Rates \- Flowcall, accessed May 2, 2026, [https://flowcall.co/blog/whatsapp-business-api-pricing-2026](https://flowcall.co/blog/whatsapp-business-api-pricing-2026)  
5. WhatsApp Business API Pricing 2026: Complete Country Guide, accessed May 2, 2026, [https://hyperleap.ai/blog/whatsapp-business-api-pricing-guide-2026](https://hyperleap.ai/blog/whatsapp-business-api-pricing-guide-2026)  
6. WhatsApp Messaging Pricing \- Twilio, accessed May 2, 2026, [https://www.twilio.com/en-us/whatsapp/pricing](https://www.twilio.com/en-us/whatsapp/pricing)  
7. 10 Best Bulk SMS Providers in 2026: Features, Pricing, and Honest Reviews \- Arkesel, accessed May 2, 2026, [https://arkesel.com/comparing-top-5-bulk-sms-providers-features-pricing/](https://arkesel.com/comparing-top-5-bulk-sms-providers-features-pricing/)  
8. How to Set Up WhatsApp Business API in 2026 (Complete Guide) \- OnSync, accessed May 2, 2026, [https://onsync.co/blog/how-to-set-up-whatsapp-business-api-2026](https://onsync.co/blog/how-to-set-up-whatsapp-business-api-2026)  
9. How to Apply for WhatsApp Business API \[Guide 2026\] \- Intellicon, accessed May 2, 2026, [https://www.intellicon.io/how-to-apply-for-whatsapp-business-api-guide-2026/](https://www.intellicon.io/how-to-apply-for-whatsapp-business-api-guide-2026/)  
10. Top 11 SMS providers for developers in 2026 \- Knock, accessed May 2, 2026, [https://knock.app/blog/the-top-sms-providers-for-developers](https://knock.app/blog/the-top-sms-providers-for-developers)  
11. Meta Business Verification for WhatsApp API: The Ultimate Fix Guide (2026) \- Zaple.ai, accessed May 2, 2026, [https://zaple.ai/blog/meta-business-verification-whatsapp/](https://zaple.ai/blog/meta-business-verification-whatsapp/)  
12. Free WhatsApp Business API Setup (2026 Guide), accessed May 2, 2026, [https://www.go4whatsup.com/how-to-set-up-a-free-whatsapp-business-api-step-by-step-guide-for-2026/](https://www.go4whatsup.com/how-to-set-up-a-free-whatsapp-business-api-step-by-step-guide-for-2026/)  
13. Gemini 3.1 Pro \- Google DeepMind, accessed May 2, 2026, [https://deepmind.google/models/gemini/pro/](https://deepmind.google/models/gemini/pro/)  
14. Gemini 3.1 Pro \- Model Card \- Google DeepMind, accessed May 2, 2026, [https://deepmind.google/models/model-cards/gemini-3-1-pro/](https://deepmind.google/models/model-cards/gemini-3-1-pro/)  
15. Gemini 3.1 PRO Preview by Google — Pricing, Specs & API Access \- Inworld AI, accessed May 2, 2026, [https://inworld.ai/models/google-ai-studio-gemini-3-1-pro-preview](https://inworld.ai/models/google-ai-studio-gemini-3-1-pro-preview)  
16. Gemini 3.1 Pro Preview pricing & specs — Google | CloudPrice, accessed May 2, 2026, [https://cloudprice.net/models/google-gemini-3-1-pro-preview](https://cloudprice.net/models/google-gemini-3-1-pro-preview)  
17. AI Models \- Puter Developer, accessed May 2, 2026, [https://developer.puter.com/ai/models/](https://developer.puter.com/ai/models/)  
18. Arabic Language AI Models Benchmark \- Multilingual LLM Performance \- Artificial Analysis, accessed May 2, 2026, [https://artificialanalysis.ai/models/multilingual/arabic](https://artificialanalysis.ai/models/multilingual/arabic)  
19. Auto-Deskew Scanned Documents with OpenCV and Python: Step-by-Step Code Example, accessed May 2, 2026, [https://www.dynamsoft.com/codepool/deskew-scanned-document.html](https://www.dynamsoft.com/codepool/deskew-scanned-document.html)  
20. Adaptive Thresholding with OpenCV ( cv2.adaptiveThreshold ) \- PyImageSearch, accessed May 2, 2026, [https://pyimagesearch.com/2021/05/12/adaptive-thresholding-with-opencv-cv2-adaptivethreshold/](https://pyimagesearch.com/2021/05/12/adaptive-thresholding-with-opencv-cv2-adaptivethreshold/)  
21. Detect Table in an Image in Python: Complete Guide \- Cloudinary, accessed May 2, 2026, [https://cloudinary.com/guides/image-effects/detect-table-in-image-python](https://cloudinary.com/guides/image-effects/detect-table-in-image-python)  
22. Gemini 3 Pro Image Preview Pricing: Complete Cost Guide for Every Budget (2026), accessed May 2, 2026, [https://blog.laozhang.ai/en/posts/gemini-3-pro-image-preview-pricing](https://blog.laozhang.ai/en/posts/gemini-3-pro-image-preview-pricing)  
23. pgvector Guide: Vector Search and RAG in PostgreSQL – Encore Blog, accessed May 2, 2026, [https://encore.dev/blog/you-probably-dont-need-a-vector-database](https://encore.dev/blog/you-probably-dont-need-a-vector-database)  
24. Using PostgreSQL as a Vector Database: a Guide \- Yugabyte, accessed May 2, 2026, [https://www.yugabyte.com/key-concepts/using-postgresql-as-a-vector-database/](https://www.yugabyte.com/key-concepts/using-postgresql-as-a-vector-database/)  
25. Hybrid Search in PostgreSQL: The Missing Manual | ParadeDB, accessed May 2, 2026, [https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual](https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual)  
26. PostgreSQL Hybrid Search Using pgvector and Cohere | Tiger Data, accessed May 2, 2026, [https://www.tigerdata.com/blog/postgresql-hybrid-search-using-pgvector-and-cohere](https://www.tigerdata.com/blog/postgresql-hybrid-search-using-pgvector-and-cohere)  
27. Gemini 3.1 Pro Preview vs GPT-5 (high): Model Comparison \- Artificial Analysis, accessed May 2, 2026, [https://artificialanalysis.ai/models/comparisons/gemini-3-1-pro-preview-vs-gpt-5](https://artificialanalysis.ai/models/comparisons/gemini-3-1-pro-preview-vs-gpt-5)  
28. Run a hybrid vector similarity search | AlloyDB for PostgreSQL | Google Cloud Documentation, accessed May 2, 2026, [https://docs.cloud.google.com/alloydb/docs/ai/run-hybrid-vector-similarity-search](https://docs.cloud.google.com/alloydb/docs/ai/run-hybrid-vector-similarity-search)  
29. How to Create Hybrid Search \- OneUptime, accessed May 2, 2026, [https://oneuptime.com/blog/post/2026-01-30-hybrid-search/view](https://oneuptime.com/blog/post/2026-01-30-hybrid-search/view)  
30. PGVector Hybrid Search: RRF & Semantic Claude Code Skill \- MCP Market, accessed May 2, 2026, [https://mcpmarket.com/tools/skills/pgvector-hybrid-search-2](https://mcpmarket.com/tools/skills/pgvector-hybrid-search-2)  
31. IVFFlat vs HNSW in pgvector with text‑embedding‑3‑large. When is it worth switching? : r/Rag \- Reddit, accessed May 2, 2026, [https://www.reddit.com/r/Rag/comments/1pijk7q/ivfflat\_vs\_hnsw\_in\_pgvector\_with/](https://www.reddit.com/r/Rag/comments/1pijk7q/ivfflat_vs_hnsw_in_pgvector_with/)  
32. pgvector/pgvector: Open-source vector similarity search for Postgres \- GitHub, accessed May 2, 2026, [https://github.com/pgvector/pgvector](https://github.com/pgvector/pgvector)  
33. Simple Memory integrations | Workflow automation with n8n, accessed May 2, 2026, [https://n8n.io/integrations/window-buffer-memory/](https://n8n.io/integrations/window-buffer-memory/)

[image1]: <data:image/png;base64,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>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAsAAAAZCAYAAADnstS2AAAA20lEQVR4XmNgGHSAA4hVgTgAiD3R5DDAHCD+D8V70OSwgqsMEMV+6BLYwFcgfgvEmugS6ICRAWLqJHQJbECQAaI4GkmMG4jVGCAGoQCQotMMEE3MQDwfiGUZIAaUI6kDA1BogBSAFJYCMSsDJAhBiouQ1IE9BPLYbyBuZoAoxAmCGCAm/IHSVxiwuBMGWhkgiliA2AOIXwNxBooKJPCcAeIEGAB5FhSLoNDYzIAWSf+A+C4SH+T7hVD2CSBWRJIDOyEZic8PxH8ZIM4BsVGAMgMkyNDFQBEyCigHAPyEJ+ztU6OxAAAAAElFTkSuQmCC>

[image3]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABMAAAAYCAYAAAAYl8YPAAAAX0lEQVR4XmNgGAWjgKpAAV2AEuABxPzoguQCkEFB6IKUgItALI8uSC7gBuLFQCyDLjENiGeRgRcA8S8g7mOgEOB0GTkA5LLt6ILkgisMVIoAFyAWRBckF7SiC4yC4QYA/C8RC4AA67MAAAAASUVORK5CYII=>