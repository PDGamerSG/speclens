# Submission materials

Repository: https://github.com/PDGamerSG/speclens

Public demo: https://speclens.pallabdas.me

**Project name:** SpecLens

**One-line description:** Visual quality inspection that learns a factory’s standards from cited human corrections using Hindsight.

**Project summary:** SpecLens gives quality engineers an inspection desk for part photos. A vision model checks the base specification, explains its decision, and identifies a defect region. When an engineer corrects that decision, SpecLens preserves the original reasoning and retains the human standard in Hindsight. The next matching inspection recalls relevant corrections with their source IDs. Memory is separated by factory, part family, and specification revision. A paired comparison fixes the image, model, and specification while showing the observed memory-off and memory-on decisions.

**Stack:** React, TypeScript, Vite, WebGL, FastAPI, SQLite, Meta vision, Hindsight HTTP retain/recall/reflect.

**Materials ready to review:**

- [Article draft](article.md)
- [LinkedIn draft and comments](social.md)
- [Video script](../demo.md)
- [Recorded 1080p demo video](SpecLens-demo-1080p.mp4) (3 minutes 28 seconds, English narration)
- [Recorded transcript](SpecLens-demo-transcript.md) and [English subtitles](SpecLens-demo-English.srt)
- [Application screenshot](../screenshots/public-inspection.png)
- [Verified public deployment](../verification.md#public-deployment)
- [Setup and deployment](../setup.md)

## Required inputs from the team

The [final submission form](https://forms.gle/7eSw5Dz2oT2MhymX7) was read without submitting it on November 7, 2026. All ten fields below are required. The form permits **one submission per team** and asks every member to agree on the final entry.

| Form field | Ready or still needed |
|---|---|
| Email ID | Team’s submission contact email |
| Phone Number | Submission contact phone number |
| Team Name (as used during registration) | Exact registered team name; this can differ from the project name SpecLens |
| Team Members (full names of all members) | Complete roster with each person’s full name |
| GitHub Repository/Google Drive Link (containing required files for verification) | Ready: `https://github.com/PDGamerSG/speclens` |
| Social Media Post on LinkedIn | Public LinkedIn post URL for each member, as required by the content guide |
| Article link | Public article URL for each member |
| Video Link | One public YouTube demo URL for the team |
| Reddit Post Link | Public URL of the article’s Reddit link post |
| FEEDBACK | Team’s answer to “Did the competition do anything really well, or are there any ways to improve?” |

Every member must also complete the [mandatory profile review form](https://forms.gle/BGcky3M6Nw1pBEPw6). The final form says teams will not be reviewed without it. This profile form requires a Google sign-in; its exact fields could not be inspected through unauthenticated read-only access. Each member should complete it in their own account and confirm completion. Do not send account passwords or session cookies.

For each member, also confirm the required download and use of [Band Desktop](https://www.band.ai/). The verified installation and connected account on this build machine do not establish another participant’s use.

## Publication requirements

The [official brief](https://docs.google.com/document/d/1A4ezag02em823ZzYF34DiUVHUNLWI5ztm70QvWidWoQ/edit) requires Hindsight, Band Desktop, documented code, a demo video, a live project demonstration, and an explanation of the memory integration. The [content guide](https://docs.google.com/document/d/1Spy4cclvZtWFI_ynXLcSDGBSVqb_Zjp2M1ffXqWeOXU/edit) specifies an **English article and social post per member, plus one team video**.

- Publish each article on a public article platform such as Medium, Dev.to, Hashnode, Substack, or LinkedIn Articles. A shared document link is insufficient. The guide’s overview says 800–1,500 words while its drafting prompt says 1,200–2,000; a 1,200–1,500-word article satisfies both. The prepared article is within that overlap. Include screenshots and the Hindsight GitHub, Hindsight documentation, and Vectorize agent-memory links already in the draft.
- Publish each LinkedIn post with the repository link in the main post. Put the article URL in the first comment and add a comment linking to `https://github.com/vectorize-io/hindsight`. Tag Code.in on LinkedIn and in the article, as the guide requests. The guide’s generated-post target is under 800 characters; the prepared main post fits.
- Share the article as a **link post** in one of `r/llmdevs`, `r/sideproject`, `r/aiagents`, or `r/aimemory`, following that community’s rules. Keep the resulting Reddit post URL.
- Record one 2–5-minute team video at **1080p minimum**, with a real inspection, correction, retain, and recall. Publish it publicly on YouTube. The guide also requests a 16:9 Nano Banana thumbnail using a photo of one or more members; provide a team photo if you want help preparing that asset.
- Articles and social posts must not contain “hackathon” in their titles, bodies, or hashtags. The supplied drafts avoid it. Keep results tied to the recorded observations; the small synthetic ablation is exploratory.

## Finish before November 7, 11:59 PM IST

- [x] Real Meta vision and Hindsight retain, recall, and reflection are recorded; automated simulations are labeled separately.
- [x] Repository, setup guide, evidence, article/social drafts, and video walkthrough are prepared.
- [x] Official Band Desktop 0.4.18 was installed and opened on the build machine; its connected account and agents were checked with `band doctor`.
- [ ] Confirm every member has completed the profile form and the required Band Desktop use.
- [ ] Collect the registered team name, contact email and phone, full roster, and feedback text.
- [ ] Personalize and publish an article and LinkedIn post for every member; collect all public URLs and add the required comments/tags.
- [x] Record the actual public SpecLens workflow in a 1080p video with English narration and subtitles. The recording uses four real vision calls and shows retain, cited recall, reflection, comparison, and saved history.
- [ ] Publish the Reddit link post and upload the prepared demo to public YouTube; collect both URLs.
- [ ] Have all members review the final entry, then submit the single team form once on the team’s behalf.

We can finish code fixes, tests, deployment checks, screenshots, draft revisions, and a completed submission worksheet from the supplied details. The team supplies personal information, confirms each member’s actual contribution and profile/Band completion, and publishes or explicitly authorizes account actions. No social posts or forms have been submitted by this build session.
