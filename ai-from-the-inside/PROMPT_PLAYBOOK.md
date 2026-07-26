# The Prompt Playbook

**Sapienza University of Rome — PhD Soft Skills 2026**

Your takeaway from the course. Fifteen rules and seven prompts.

The tools you used today will be replaced within a year or two. These will not be, because
they are consequences of how the machinery works, not features of any one product.

**This document is yours.** Add to it. Delete what turns out not to work for your field.
Keep it in the same place you keep your other research methods.

---

## Part 1 — The fifteen rules

Each one was earned in a specific moment of the course. The reason matters more than
the rule, so the reason is given.

### Before you start

**1. If you can write the rule, write the rule.**
Machine learning exists for problems where the rules cannot be written down. Using AI where
an ordinary rule would do is not sophistication — it is slower, more expensive, less auditable
and less correct.

**2. Ask whose judgement is encoded in the answers.**
Every model reproduces the labels it was trained on, and those labels were assigned by people,
under time pressure, following a guideline document that was itself a compromise. "Ground truth"
is a confident name for somebody's opinion.

**3. Never accept an accuracy number without the baseline and the failure cases.**
A detector for something that occurs 5% of the time can be 95% accurate by always saying "no".
The first question about any performance figure is: *what would a system that does nothing score?*

### While you work

**4. Ask the machine to show what it got wrong, and which features it used.**
Two prompts that turn a black box into something you can judge. The mistakes tell you whether
the task is well-defined; the features tell you whether it found a concept or a shortcut.

**5. When a model performs suspiciously well, hunt the shortcut before celebrating.**
It learned that images with a ruler are malignant, that huskies have snow behind them, that
one collection was digitised on one scanner. Shortcuts score beautifully on your test set.

**6. Give it the material. Ask it to transform, not to remember.**
The single most useful distinction in the course.
*Recall* ("what did Gramsci say about hegemony?") queries a lossy compression of the internet
and you cannot see where it is lossy.
*Transformation* ("here is the passage — summarise its argument in three claims") works on
material you supplied and can check in seconds.

**7. Self-checking is worth a prompt and is never verification.**
Asking a model to review its own output genuinely improves it on average. It never converts an
unverified claim into a verified one. Only a source you opened yourself does that.

**8. When a conversation goes wrong, start a new one.**
A chatbot resends the entire transcript every turn. A wrong statement stays on the desk and is
re-read as established fact for every subsequent turn. Arguing with it adds contradiction to the
transcript; starting fresh clears the desk. This is not superstition — it is the correct fix.

**9. Write rules as procedures, not prohibitions.**
"Never invent citations" is weak. "For each claim, quote the passage it comes from, then interpret
it" is strong, and measurably so. Give it something to *do*, not something to avoid.

**10. Ask for the evidence before the conclusion.**
Each token is generated conditioned on the text so far, so writing out the evidence first
literally puts better material in front of the model. It also makes the answer checkable.
Two benefits from one sentence.

**11. Never accept a first output. Make it attack its own work.**
See the verification prompt in Part 2. Use it to end every session that matters.

**12. Test grounded systems on facts you already know — including one they should not be able
to answer.**
Everybody tests that a document assistant answers correctly. Almost nobody tests that it admits
ignorance. A system that never says "the provided passages do not answer this" is not a research
tool; it is a generator of confident text.

**13. Agents are for narrow, repetitive, verifiable tasks at a scale you cannot do by hand.**
"Extract the dates from these 42 letters" succeeds. "Research my topic" does not. If you cannot
name the columns of the output table, you do not yet have a task.

**14. For anything non-trivial, make it state its assumptions before it acts.**
The assumptions are where the failures live — that all your files are in one folder, that every
PDF has a text layer, that dates come in one format.

**15. Your prompts are research instruments. Version them, document their limits, reuse them.**
Keep one file of prompts that worked, with a line above each on what it is for and when it fails.
When one disappoints, edit it *there* — do not start again in a chat window. This is the
difference between someone who has used AI for two years and someone who has got *better* at it
for two years.

---

## Part 2 — The seven prompts

Copy these. They are written to be used verbatim, with the angle-bracketed parts replaced.

### The anatomy every prompt should have

| Part | What it does |
|---|---|
| **Role & context** | Who is asking, for what, at what level |
| **The material** | The actual text or data — without this you are querying its memory |
| **The task** | One unambiguous verb: summarise, extract, classify, compare, critique |
| **The form** | Exact output shape: these columns, three bullets, this JSON |
| **The escape hatch** | What to do when it cannot comply — **never omit this** |

Without an escape hatch, the most likely continuation of a question is an answer. So it
produces one, whether or not it has grounds.

---

### 1. The structured extraction

```text
Read the text between the triple quotes.

Produce a table with exactly these columns:
<column> | <column> | <column>

Rules:
- One row per <unit: paragraph / person / event>.
- Use only the text. Anything not stated: NOT STATED.
- For each row, add a final column quoting the exact words you based it on.

"""
<text>
"""
```

**Why it works.** The quotation column makes every cell traceable to a passage. You can verify
twenty rows in the time it takes to read one paragraph of prose. Structure is not a formatting
preference — it is an error-detection device.

---

### 2. The hostile reviewer

```text
Below is a passage from my thesis.

Act as the most demanding examiner in my field.
Do not praise anything. Do not summarise it back to me.

1. List every claim I make that I have not supported.
2. For each, name the specific evidence a reviewer would demand.
3. Name the strongest counter-argument I have not addressed.
4. Identify where I have overstated: quote the exact phrase and suggest
   what it should say instead.

"""
<passage>
"""
```

**Why it works.** "Do not praise anything" is doing the real work. Models are tuned on human
preference data, and humans preferred agreeable answers — so agreeableness was trained in.
Without an explicit adversarial instruction you get encouragement and one weak suggestion.

---

### 3. The interrogation, reversed

```text
I want to <goal>.

Do not give me a plan yet.

First, ask me the five questions whose answers would most change your
advice. Ask them one at a time, and wait for my answer before the next.

Only after all five, give me your recommendation.
```

**Why it works.** A generic question produces a generic answer. Forcing it to interrogate you
surfaces the constraints you forgot to mention. "One at a time, wait" matters — without it you
get five questions at once and answer them all badly.

Best for: research design, methods choices, scoping a chapter.

---

### 4. The parallel-column check

```text
Below is a source text and my translation.

Produce a table: Source segment | My translation | Issue | Severity

For every segment, mark:
- MEANING  if my version changes the sense
- OMISSION if something in the source is not rendered
- ADDITION if my version adds what is not in the source
- REGISTER if the tone or formality differs
- OK       if none apply

Do not rewrite my translation. Only diagnose it.
```

**Why it works.** "Do not rewrite" keeps you the author. A diagnosis you can act on beats a
replacement text you would have to check line by line anyway.

Adapt the categories to your discipline: they work equally well for coding qualitative data,
checking a transcription, or reviewing a summary against its source.

---

### 5. The normaliser with a receipt

```text
Here is a column of <place names / titles / dates> transcribed from
manuscripts, with inconsistent spelling, abbreviations and Latin forms.

For each entry produce: Original | Normalised | Confidence | Why

- Confidence is HIGH, MEDIUM or LOW.
- LOW for anything you are guessing at.
- If an entry could be two different <places>, list both and mark it
  AMBIGUOUS. Do not choose.
```

**Why it works.** The confidence column turns an unusable output into a workflow: check the LOW
and AMBIGUOUS rows by hand, spot-check the HIGH ones.

**The general principle: always make it tell you where it is unsure.** An output with no
uncertainty markers must be checked entirely. One with them can be checked *selectively* —
which is the difference between a tool that saves time and one that merely relocates it.

---

### 6. The specification-first build

```text
Before writing any code, write back to me:

1. Your understanding of what I want, in your own words.
2. The three assumptions you are making that I did not state.
3. The edge cases you expect to cause trouble.

Then wait. Do not write code until I confirm.
```

**Why it works.** Ninety seconds that routinely saves twenty minutes. Point 2 is where you
discover it has assumed something ruinous.

---

### 7. The verification prompt — end every session with this

```text
Before I rely on this, act as a hostile reviewer of your own output.

1. List every claim you made that is not directly supported by the text
   I gave you.
2. List the three most likely ways this gives a wrong answer without
   obviously failing.
3. Tell me which specific input would break it.
4. Do not defend your work. Only find problems.
```

**Why it works.** The most reusable prompt in the course. It applies to text, code, plans and
arguments equally. Point 4 is not optional.

---

## Part 3 — Building things by prompting

You do not need to write code. You do need to run this loop.

1. **Describe the outcome, not the method.** "One row per file with these columns" — not "use a
   loop and a dictionary". You do not know the method. That is fine, and it is the point.
2. **Ask for the smallest version first.** Get one file working before you ask for the folder.
3. **Run it. Read the output, not the code.** Is the answer right on a case you can check by hand?
4. **Paste errors back verbatim.** The whole red message. Do not summarise it, do not retype it.
5. **Ask it to prove itself.** "Show me three cases where this could go wrong, and test them."

### The four failures you will meet

| Failure | What it looks like | The fix |
|---|---|---|
| **Invented library** | Import error for a plausible package that doesn't exist | Paste the error back; "use only standard, widely available libraries" |
| **Silent partial work** | Processes 3 files of 300, reports success | Always ask it to print counts |
| **Fixing by deleting** | Asked to fix an error, it removes the failing feature | "Keep all previous behaviour and fix only the error" |
| **Works on the example only** | Fine on the clean sample, useless on your real files | Test on your ugliest real case early, not last |

---

## Part 4 — Before this goes anywhere near your thesis

**Declare it.** Sapienza, your journal and your funder each have a policy. Read them before you
need them, not after.

**Verify every factual claim yourself.** Every citation opened — the paper, not the abstract.
Every quotation checked against the source. No exceptions. Fabricated citations have ended
careers and produced court sanctions, and they are convincing precisely because a plausible
citation and a real one are indistinguishable to the machinery that produced them.

**Record what you did.** Which model, which version, which prompts, which date. Outputs are not
reproducible — temperature makes them a dice roll, and models are updated and withdrawn without
notice. Your *method* must be reproducible even when the output is not. "I used ChatGPT" is not
a method section.

**Think before uploading.** Interview transcripts, unpublished work, personal data, material
under embargo. Check what the service does with what you send it. If the answer is unclear or
unacceptable, that is the argument for running models on the University's own machines.

---

## Part 5 — The three questions to ask of any AI tool you are sold

Whether it is a commercial product, a collaborator's pipeline, or a paper you are refereeing:

1. **What was it trained on, and who is missing from that data?**
2. **How was it evaluated — on data genuinely held out, against what baseline?**
3. **On what kind of input does it fail, and did anyone look?**

If the answer to the third is "we haven't found any failures", they haven't looked.

---

*Sapienza PhD Soft Skills 2026. Reuse, adapt and pass this on.*
