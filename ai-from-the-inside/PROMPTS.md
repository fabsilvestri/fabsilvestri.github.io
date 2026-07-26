# PROMPTS

Every prompt used in the course, in the order it appears.

**This file is generated** by `notebooks/build_notebooks.py` from the same source as the notebooks, so it can never drift out of step with them. Edit the generator, not this file.

Two kinds of prompt appear here:

| Where it goes | What it does |
|---|---|
| **code cell** | Typed into Colab's AI (`Ctrl`+`Shift`+`Enter`) so it writes code for you. |
| **AI chat panel** | Typed into the Colab AI sidebar, where you are talking to the model itself. |

---

## Contents

- [Notebook 0 — Warm-up](#notebook-0-warm-up)
- [Notebook 1 — Teach a machine to sort your texts](#notebook-1-teach-a-machine-to-sort-your-texts)
- [Notebook 2 — Images, and how to fool them](#notebook-2-images-and-how-to-fool-them)
- [Notebook 3 — Look inside the language model](#notebook-3-look-inside-the-language-model)
- [Notebook 4 — Build a chatbot with a method](#notebook-4-build-a-chatbot-with-a-method)
- [Notebook 5 — The prompt tournament](#notebook-5-the-prompt-tournament)
- [Notebook 6 — Question your own documents](#notebook-6-question-your-own-documents)
- [Notebook 7 — Build your research agent (capstone)](#notebook-7-build-your-research-agent-capstone)

---

## Notebook 0 — Warm-up

### 2 · Your first generated cell

*Goes in: code cell*

```text
Print a friendly one-line greeting, then print today's date in a
human-readable form, and finally print how many days remain in this year.
```

**Why:** Read what it wrote before you run it. Getting into that habit now is the whole point of the exercise.

<br>

## Notebook 1 — Teach a machine to sort your texts

### 1 · Look at your data before anything else

*Goes in: code cell*

```text
Load the file letters.csv into a table.
Show me its shape, the column names, and 10 random rows
with the full text visible.
Also show how many letters carry each label.
```

**Why:** Never train anything before you have looked at the data. You are checking: is it what I think it is?

<br>

### 2 · Train and evaluate — the whole of machine learning, in one prompt

*Goes in: code cell*

```text
Split the data 80/20 into a training set and a test set, keeping the
balance of labels the same in both.
Train a simple text classifier on the training set only.
Report its accuracy on the test set.
Use the 'label' column, not 'true_label'.
```

**Why:** Note the last line. The file also contains `true_label`, which is the label *before* we introduced realistic noise. Using it would be cheating — and it is exactly the kind of leak that ruins real studies.

<br>

### 3 · The baseline — the number nobody reports

*Goes in: code cell*

```text
What accuracy would I get on the same test set by ignoring the text
completely and always predicting the most common label?
Print that number next to the model's accuracy so I can compare them.
```

**Why:** **If these two numbers are close, your model has learned nothing.** Ask this of every accuracy figure you ever meet, including in papers you referee.

<br>

### 4 · Read the mistakes

*Goes in: code cell*

```text
Show me 8 test letters the model got wrong.
For each one show the full text, the true label and the predicted label,
in a readable layout — not a cramped table.
```

**Why:** Read them properly. Ask yourself: *would I have got this right?* Some of them are mislabelled, and some are genuinely ambiguous. This is the most valuable five minutes in the notebook.

<br>

### 5 · What did it actually learn?

*Goes in: code cell*

```text
Show me the 15 words or phrases that push the model most strongly towards
each of the two labels. Display them as a horizontal bar chart, with the
two labels in different colours.
```

**Why:** Look for anything embarrassing: a greeting, a place name, a punctuation habit. If the model keys on something that has nothing to do with the concept, it found a **shortcut**, not a meaning.

<br>

### 6 · How much data did it actually need?

*Goes in: code cell*

```text
Retrain the same kind of model on only the first 20 training letters,
then on 50, then on 100, then on all of them.
Plot test accuracy against the number of training examples,
and draw the do-nothing baseline as a horizontal line.
```

**Why:** This curve is how you answer 'do I need to label more data?' — a question that costs real money in real projects.

<br>

### 7 · Train on nonsense

*Goes in: code cell*

```text
Randomly shuffle the training labels so they no longer match their letters,
then train the same kind of model on that shuffled data.
Report BOTH the training accuracy and the test accuracy,
and print the do-nothing baseline next to them for comparison.
```

**Why:** Expect training accuracy near 100% and test accuracy near the baseline. The model happily memorised 211 arbitrary pairings and learned nothing whatsoever.

<br>

## Notebook 2 — Images, and how to fool them

### 1 · Build an image classifier

*Goes in: code cell*

```text
Load the built-in handwritten digits dataset from scikit-learn.
Show me 10 example images with their labels.
Then train a classifier on 80% of the data and report its
accuracy on the remaining 20%.
Finally show a grid of the images it got wrong, each labelled
with the true digit and what it guessed.
```

<br>

### 2 · Add noise and watch confidence stay high

*Goes in: code cell*

```text
Add faint random noise to the test images and report the accuracy again.
Then, for the noisy images it got WRONG, show me how confident it was
in its wrong answer. Plot the distribution of that confidence.
Show a few of the noisy images next to the clean originals.
```

**Why:** Watch what happens: accuracy falls substantially, and confidence barely moves. **The model has no way of telling you that it has left familiar territory.**

<br>

## Notebook 3 — Look inside the language model

### 1 · Split text into real tokens

*Goes in: code cell*

```text
Install and use the tiktoken library.
Take this sentence: 'The archivist catalogued an unremarkable manuscript.'
Split it into tokens and print each token with its number,
one per line, so I can see exactly where the splits fall.
Then print how many tokens it used and how many words it had.
```

**Why:** `tiktoken` is a small, fast library with no heavy dependencies. It is the actual tokenizer used by several production models.

<br>

### 2 · The language tax

*Goes in: code cell*

```text
Using the same tokenizer, compare how many tokens are needed for the
same meaning in different languages. Use these sentences:
  English: 'The archivist catalogued an unremarkable manuscript.'
  Italian: 'L'archivista ha catalogato un manoscritto non degno di nota.'
  Greek:   'Ο αρχειοφύλακας κατέγραψε ένα ασήμαντο χειρόγραφο.'
Show the token count for each as a bar chart, and also show the
tokens-per-character ratio.
```

**Why:** The same meaning costs more tokens in Italian than English, and far more in Greek. That is a direct cost in money, in context-window space, and in reliability — and it falls hardest on exactly the material this room works with.

<br>

### 3 · Build a tiny next-word predictor

*Goes in: code cell*

```text
Using the text column of letters.csv, count which words follow which
pairs of words. This gives a simple next-word predictor.
Then, for the phrase 'I write to', show me the top 10 candidates for
the next word with their probabilities, as a horizontal bar chart.
Use only plain Python and pandas — no neural networks.
```

**Why:** This is a *trigram model*. Real language models replaced this approach, but the output — a ranked list of candidates with probabilities — is exactly what a modern model produces too, just over 100,000 fragments instead of a few thousand words.

<br>

### 4 · Generate at different temperatures

*Goes in: code cell*

```text
Using the next-word predictor from the previous cell, write a function that
generates 25 words starting from 'I write to', choosing each next word
randomly according to its probability, adjusted by a temperature setting.
Generate 3 samples at temperature 0.2, 3 at temperature 1.0, and
3 at temperature 2.0. Print them grouped and clearly labelled.
```

**Why:** Read the three groups side by side. Low temperature repeats itself; high temperature produces confident nonsense. This is the same dial you set when you use any commercial model — and it is why the same question can give you different answers.

<br>

### 5 · Count it properly

*Goes in: code cell*

```text
Count how many times each letter appears in the word 'strawberry',
and show how the tiktoken tokenizer splits that same word.
Print the two results side by side.
```

**Why:** Then go and ask the Colab AI chat panel the same question in words. Compare its answer to the count you just computed.

<br>

### 6 · Ask for citations in your own narrow specialism

*Goes in: AI chat panel*

```text
Give me five peer-reviewed articles about <the narrowest topic in your
own PhD that you can state in one line>. For each one give the authors,
the title, the journal, the year, and the DOI.
```

**Why:** **Use your own genuinely narrow topic.** A general topic gives you real citations and the lesson is lost. The narrower and more specialised, the sharper the result.

<br>

### 7 · Ask it to mark its own work

*Goes in: AI chat panel*

```text
For each of the five citations you just gave me, tell me how confident you
are that it exists, and mark any that you may have constructed rather than
recalled. Be blunt. Do not defend your earlier answer.
```

**Why:** Sometimes this works remarkably well. Sometimes it defends fiction with complete confidence. **The fact that you cannot tell which in advance is the entire point.** Self-checking is worth a prompt. It is never verification.

<br>

## Notebook 4 — Build a chatbot with a method

### 1 · Build the conversation machinery

*Goes in: code cell*

```text
Build a simple chat transcript in this notebook:
- a list of messages, each with a role (system, user, assistant) and text
- a function add(role, text) that appends to it
- a function show() that prints the whole transcript in a readable form
- a function to_send() that prints exactly what would be sent to a model
  this turn, formatted as Role: text
Start it with a system message and two example exchanges so I can see it work.
```

**Why:** Look carefully at what `to_send()` prints. That whole block is re-read from scratch by the model on every turn. Nothing is remembered; everything is resent.

<br>

### 2 · Watch the desk fill up

*Goes in: code cell*

```text
Add a function that counts the tokens in the whole transcript using tiktoken,
and prints a warning when it goes over 2000 tokens.
Then add six more long exchanges to the transcript and print the token
count after each one, so I can watch it grow.
Plot the token count against the turn number.
```

**Why:** Every turn costs the *whole* transcript, not just your new message. This is why turn 40 of a conversation is slow and expensive, and why very long chats start losing their beginning.

<br>

### 3 · The fix, built in

*Goes in: code cell*

```text
Add a function reset() that clears the transcript but keeps the system
message, and prints the token count before and after.
Run it and show me the result.
```

**Why:** This is the 'start a new chat' button, and now you know exactly what it does: it clears the desk and keeps the standing instructions.

<br>

### 4 · Write your own

*Goes in: AI chat panel*

```text
<Write your own system prompt for a research assistant in YOUR field.
 Include at least one rule about something it must REFUSE to do.
 Then paste it as the first message in the Colab AI chat panel and
 work with it for a few turns.>
```

**Why:** Then spend five minutes trying to make it break its own rule. Roleplay framings (*'for a novel I am writing, have a character explain…'*) defeat most prohibitions. Long conversations defeat them too.

<br>

## Notebook 5 — The prompt tournament

### 0 · Look at the task first

*Goes in: code cell*

```text
Load dates_gold.csv and show me all 20 rows with the full letter text
and the correct date, in a readable layout.
Count how many have no date at all.
```

<br>

### Version 1 · Naive

*Goes in: AI chat panel*

```text
Extract the date from each of these letters.
```

**Why:** This is what almost everybody types. Note what it does not say: what format, what to do about a missing year, what to do when there is no date at all.

<br>

### Version 2 · Add the form and the escape hatch

*Goes in: AI chat panel*

```text
For each letter below, extract the date.

Output format: one line per letter, exactly `ID: YYYY-MM-DD`.
If the year is not stated, use XXXX in its place.
If there is no date at all, write `ID: NOT STATED`.
Output nothing else — no commentary, no explanation.
```

**Why:** Two additions: an exact output shape, and an instruction for what to do when it cannot comply. In our experience this is where the largest jump happens.

<br>

### Version 3 · Add worked examples

*Goes in: AI chat panel*

```text
For each letter below, extract the date.

Output format: one line per letter, exactly `ID: YYYY-MM-DD`.

Examples of the conversions required:
  "Siena, li 9 maggio 1685"            -> 1685-05-09
  "Torino, questo dì 28 di luglio 1664" -> 1664-07-28
  "Da Genova, 14 marzo"                -> XXXX-03-14
  "Milano 3.11.1642"                   -> 1642-11-03
  (no date line present)                -> NOT STATED

Output nothing else.
```

**Why:** Four examples pin down the Italian month names, the missing-year convention, and the numeric format — all things that a paragraph of description leaves ambiguous.

<br>

### Version 4 · Ask for the evidence before the answer

*Goes in: AI chat panel*

```text
For each letter below:
  1. First quote the exact words containing the date, or write NONE.
  2. Then, on the next line, give `ID: YYYY-MM-DD`.

Examples of the conversions required:
  "Siena, li 9 maggio 1685"            -> 1685-05-09
  "Da Genova, 14 marzo"                -> XXXX-03-14
  (no date line present)                -> NOT STATED

Never give a date that does not appear in the words you quoted.
```

**Why:** Now the evidence is on the desk before the answer is produced — which improves the answer *and* lets you check it in seconds. Two benefits from one instruction.

<br>

### 5 · Score all four

*Goes in: code cell*

```text
I will paste each set of answers as one long string, one answer per line
in the form 'ID: DATE'. Write code that pulls the ID and the date out of
each line with a regular expression, ignoring any other text on the line,
and compares them against the correct_date column of dates_gold.csv.
Show accuracy for all four versions as a bar chart, and print every case
where version 4 was right and version 1 was wrong.
```

**Why:** Note *ignoring any other text on the line*: version 4 also outputs quoted evidence, so the scorer has to cope with lines that are not just answers. The reference cell below already handles that.

<br>

## Notebook 6 — Question your own documents

### 1 · Extract, and check what you got

*Goes in: code cell*

```text
Read every PDF in the pdfs folder and every .txt file in the archive folder.
For each one report: filename, number of pages (for PDFs), and
number of characters of text extracted.
If a file yields no text at all, print 'NO TEXT LAYER' for it and
carry on with the others — do not stop the whole run.
Show the results as a table, sorted by character count ascending.
```

**Why:** **Read that table before going any further.** Sorting ascending puts the failures at the top where you cannot miss them. A file with 0 characters is a file that will be invisible to everything that follows.

<br>

### 2 · Chunk, keeping provenance

*Goes in: code cell*

```text
Split the text of every document into passages of about 120 words with
30 words of overlap between consecutive passages.
Number the passages, and for each one keep a record of which file it
came from and its position in that file.
Show me how many passages there are in total, and print passages 0, 1
and 2 in full so I can check the overlap is working.
```

**Why:** Provenance is what makes a citation mean something later. Without it you get an answer with a number attached that you cannot trace back to anything.

<br>

### 3 · Build the search, and test it on its own

*Goes in: code cell*

```text
Turn every passage into a vector using TF-IDF followed by TruncatedSVD
with 100 components, then normalise the vectors.
Write a function search(question, k=5) that returns the k most similar
passages by cosine similarity, with their similarity scores, their
passage numbers and their source filenames.
Test it with the question 'a prisoner held without charge' and print
the results, and warn me if the best similarity score is below 0.15.
```

**Why:** **Test retrieval before you connect it to anything.** If the search is bad, the answers will be confidently wrong and you will blame the wrong component.

<br>

### 4 · Build the prompt assembler

*Goes in: code cell*

```text
Write a function ask(question) that:
  1. retrieves the 5 most relevant passages
  2. builds a single block of text containing, in this order:
     - the instruction below
     - the numbered passages, each with its source filename
     - the question
  3. prints that block so I can copy it into the AI chat panel

The instruction must read:
  Answer using ONLY the passages below. After every statement, cite the
  passage number it came from, like [3]. If the passages do not contain
  the answer, reply exactly: 'The provided passages do not answer this.'
  Do not use anything you know from outside these passages.
```

**Why:** Notice that you are specifying the *architecture* of a retrieval system in plain English. That is the whole skill.

<br>

### 5 · Test that it can say no

*Goes in: AI chat panel*

```text
<Ask your system a question you are certain the documents cannot answer.
 For the provided archive, try: 'What did the Bishop say about the
 printing press in Amsterdam?'>
```

**Why:** The correct answer is *'The provided passages do not answer this.'* If you get anything else, your instruction is not strong enough — go back and strengthen it, then test again.

<br>

## Notebook 7 — Build your research agent (capstone)

### 2 · Build the tools

*Goes in: code cell*

```text
I want to build a supervised agent in this notebook.

GOAL: for every file in my source folder, produce one row with these
columns: <YOUR COLUMNS HERE>

Build me four separate tools, each as its own function, each printing
what it did:
  1. list_files()      - list the source files, print how many
  2. read_file(name)   - return its text, print the length
  3. make_prompt(text) - build an extraction prompt asking for the
                         columns above as JSON, using NOT STATED for
                         anything the text does not say
  4. add_row(data)     - append to a results table, print the running
                         count of rows so far

Also give me a variable that tracks which file we are on, so I can
process them one at a time and stay in control.

Do not process everything at once. Stop after each file.
```

**Why:** The last two lines are the entire human-in-the-loop architecture, expressed as a requirement in plain English. You are specifying a system design without writing code.

<br>

### 4 · Make it attack the table

*Goes in: AI chat panel*

```text
Look at the results table we have built. List every way it might be wrong
or incomplete. Show me the three rows you are least confident about and
say why. Then name the specific kind of document that would break this
extraction entirely.

Do not defend the work. Only find problems.
```

**Why:** *Do not defend the work* is doing real work in that prompt. Without it, the trained-in agreeableness gives you reassurance instead of a review.

<br>

### 5 · Save what you built

*Goes in: code cell*

```text
Save the results table to a CSV file and download it to my computer.
Print the number of rows saved and list any columns that are entirely
NOT STATED, since those are the ones my extraction failed on.
```

**Why:** The columns that are entirely NOT STATED tell you where the *prompt* failed, not where the documents were silent. That distinction is worth knowing.

<br>

---

## The six reusable patterns

These are not tied to any exercise. They are the ones worth keeping after today — the full versions, with commentary, are in `playbook/PROMPT_PLAYBOOK.md`.

### Pattern 1 — The structured extraction

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

**Why:** The quotation column is what makes this usable in research: every cell becomes traceable to a passage, so you can verify twenty rows in the time one paragraph would take to read.

<br>

### Pattern 2 — The hostile reviewer

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

**Why:** "Do not praise anything" is doing the real work. Without it, the agreeableness that was trained into the model gives you a paragraph of encouragement and one weak suggestion. Probably the single most useful prompt in the course for a doctoral student.

<br>

### Pattern 3 — The interrogation, reversed

```text
I want to <goal>.

Do not give me a plan yet.

First, ask me the five questions whose answers would most change your
advice. Ask them one at a time, and wait for my answer before the next.

Only after all five, give me your recommendation.
```

**Why:** Inverts the usual failure — a generic answer produced by a generic question. Forcing it to interrogate you first surfaces the constraints you forgot to mention. The "one at a time, wait" instruction matters: without it you get five questions at once and answer them all badly.

<br>

### Pattern 4 — The parallel-column check

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

**Why:** "Do not rewrite" keeps you the author. You get a diagnosis you can act on rather than a replacement text you would have to check line by line anyway. Adapt the categories to your own discipline.

<br>

### Pattern 5 — The normaliser with a receipt

```text
Here is a column of <place names / titles / dates> transcribed from
manuscripts, with inconsistent spelling, abbreviations and Latin forms.

For each entry produce: Original | Normalised | Confidence | Why

- Confidence is HIGH, MEDIUM or LOW.
- LOW for anything you are guessing at.
- If an entry could be two different <places>, list both and mark it
  AMBIGUOUS. Do not choose.
```

**Why:** The confidence column turns an unusable output into a workflow: check the LOW and AMBIGUOUS rows by hand, spot-check the HIGH ones. This is the difference between a tool that saves time and one that merely relocates it.

<br>

### Pattern 6 — The specification-first build

```text
Before writing any code, write back to me:

1. Your understanding of what I want, in your own words.
2. The three assumptions you are making that I did not state.
3. The edge cases you expect to cause trouble.

Then wait. Do not write code until I confirm.
```

**Why:** Ninety seconds that routinely saves twenty minutes. Point 2 is where you discover it has assumed something ruinous — that your files are all in one folder, that every PDF has a text layer, that dates are in one format.

<br>

### The verification prompt — use this to end every session

```text
Before I rely on this, act as a hostile reviewer of your own output.

1. List every claim you made that is not directly supported by the text
   I gave you.
2. List the three most likely ways this gives a wrong answer without
   obviously failing.
3. Tell me which specific input would break it.
4. Do not defend your work. Only find problems.
```

**Why:** The most reusable thing in the entire course. It applies equally to text, code, plans and arguments. Point 4 is not optional — without it you get reassurance.

<br>
