# PROMPTS

Every prompt used in the course, in the order it appears.

**This file is generated** by `notebooks/build_notebooks.py` from the same source as the notebooks, so it can never drift out of step with them. Edit the generator, not this file.

Two kinds of prompt appear here:

| Where it goes | What it does |
|---|---|
| **code cell** | Typed into Colab's AI (`Ctrl`+`Shift`+`Enter`) so it writes code for you. |
| **AI chat panel** | Typed into the Colab AI sidebar, where you are talking to the model itself. |

Some cells are not prompts at all — a few ask you to paste a model's reply back into the notebook, or to write something of your own. Those are marked in the notebooks and are not reproduced here.

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

### 2. Now let the AI write a cell for you

*Goes in: code cell*

```text
Print a friendly one-line greeting, then print today's date in a
human-readable form, and finally print how many days remain in this year.
```

**Why:** **The empty cell is directly below this box** — the grey one saying *Start coding or generate with AI*. Click inside it, press `Ctrl`+`Shift`+`Enter` (Mac: `Cmd`+`Shift`+`Enter`) or hover and click **Generate**, then paste the prompt. Read what it wrote before you run it — that habit is the whole point of the exercise.

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
Using the letters.csv data, split it 80/20 into a training set and a test
set, keeping the balance of labels the same in both.
Train a TF-IDF + logistic regression text classifier on the training set
only, and call the fitted model `model`.
Report its accuracy on the test set and store it in a variable called `acc`.
Use the 'label' column as the answer, not 'true_label'.
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
For each one show the full text, the label recorded in the 'label' column,
and the label the model predicted, in a readable layout — not a cramped table.
Do not use the 'true_label' column.
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

**Why:** Look closely at *what kind* of words these are. You will probably not see `beg` and `inform`. You are more likely to see pronouns, tenses and little grammatical words — `my`, `you to`, `being` on one side; `was`, `were`, `took` on the other.

That is the finding. The model never learned what a petition *is*. It learned that asking is written in the present and future and points at *you*, while reporting is written in the past. A real regularity — and a much shallower one than the label name suggests. Watch too for a place name or a date fragment sneaking in: that would be a pure **shortcut**, with nothing to do with the concept.

<br>

### 6 · How much data did it actually need?

*Goes in: code cell*

```text
Retrain the same kind of model on only the first 20 training letters,
then on 50, then on 100, then on 150, then on all of them.
Plot test accuracy against the number of training examples,
and draw the do-nothing baseline as a horizontal line.
```

**Why:** This curve is how you answer 'do I need to label more data?' — a question that costs real money in real projects.

Expect it to climb steeply and then **flatten**, and do not be alarmed if the last point dips slightly below the one before: with only 53 test letters, each point carries a margin of error of several percentage points. A flat tail is the useful answer — it means more labelling would buy you very little.

<br>

### 7 · Train on nonsense

*Goes in: code cell*

```text
Randomly shuffle the training labels so they no longer match their letters,
then train a text classifier on that shuffled data. Give this one plenty of
freedom to memorise: use LogisticRegression with C=100.
Repeat the whole thing 20 times with 20 different shuffles, and report the
AVERAGE training accuracy and the AVERAGE test accuracy, with the
do-nothing baseline next to them.
```

**Why:** **Why twenty times?** The test set is only 53 letters, so a single run has a margin of error of about 7 percentage points — one run tells you almost nothing. Averaging twenty runs is the difference between a number and a measurement, and that is itself one of the lessons.

<br>

## Notebook 2 — Images, and how to fool them

### 1 · Build an image classifier

*Goes in: code cell*

```text
Load the built-in handwritten digits dataset from scikit-learn.
Show me 10 example images with their labels.
Then split 80/20 and train a LOGISTIC REGRESSION classifier on the
training part, and report its accuracy on the held-out 20%.
Keep the fitted model in a variable called `clf`.
Finally show a grid of the test images it got wrong, each labelled
with the true digit and what it guessed.
```

**Why:** The model type is pinned deliberately. Different classifiers behave very differently in the second half of this notebook — a random forest, for instance, *does* lose confidence under noise, which would demonstrate the opposite of the point being made.

<br>

### 2 · Add noise, and compare confidence before and after

*Goes in: code cell*

```text
Add Gaussian noise with standard deviation 4.0 to the test images
(the pixel scale runs 0 to 16), and clip the result back into that range.

Then print a small table comparing CLEAN versus NOISY:
  - accuracy on each
  - the model's MEAN CONFIDENCE on each (the highest predicted
    probability, averaged over all test images)
Print how many percentage points each one dropped.

Then plot the distribution of the model's confidence in its WRONG
answers on the noisy images, and show a few noisy images next to
their clean originals.
```

**Why:** The noise level is pinned because the demo only works in a narrow band: at sd=2 accuracy barely moves and there is nothing to see; at sd=8 the digits are destroyed and the failure is unsurprising.

<br>

## Notebook 3 — Look inside the language model

### 1 · Split text into real tokens

*Goes in: code cell*

```text
Install and use the tiktoken library. Get the 'cl100k_base' encoding
and keep it in a variable called `enc`.
Take this sentence: 'The archivist catalogued an unremarkable manuscript.'
Split it into tokens and print each token with its number, one per line,
so I can see exactly where the splits fall.
Then print how many tokens it used and how many words it had.
```

**Why:** `tiktoken` is small and fast and pulls in no deep-learning framework. It is the actual tokenizer used by several production models. The variable name is pinned because later sections reuse it.

<br>

### 2 · The language tax

*Goes in: code cell*

```text
Using the tiktoken 'cl100k_base' encoding, compare how many tokens are
needed for the same meaning in three languages. Use these sentences,
and mind the apostrophe in the Italian one - use double quotes around it:
  English: "The archivist catalogued an unremarkable manuscript."
  Italian: "L'archivista ha catalogato un manoscritto non degno di nota."
  Greek:   "Ο αρχειοφύλακας κατέγραψε ένα ασήμαντο χειρόγραφο."
Show the token count for each as a bar chart, and print the
tokens-per-character ratio for each.
```

**Why:** The quoting note is there for a reason: `'L'archivista'` ends the string at the apostrophe and produces a syntax error. If that happens to you, paste the red message back to the AI — it is a good first taste of the debugging loop.

<br>

### 3 · Build a tiny next-word predictor

*Goes in: code cell*

```text
Using the text column of letters.csv, count which words follow which
single word. Store it as a dictionary called `nxt` mapping each word to
a Counter of the words that follow it. Lowercase everything, and treat
. , ; : as separate words.

Then write a function distribution(word) that returns the most likely
next words with their probabilities. If the word never appears, print a
clear message saying so rather than failing.

Show me the top 10 candidates after the word 'the', with their
probabilities, as a horizontal bar chart.
Use only plain Python, pandas and matplotlib — no neural networks.
```

**Why:** This is a *bigram model*. Real language models replaced this approach long ago, but the output — a ranked distribution over what comes next — is exactly what a modern model produces too, just over 100,000 fragments instead of a few hundred words.

<br>

### 4 · Generate at different temperatures

*Goes in: code cell*

```text
Using the `nxt` predictor from the previous cell, write a function that
generates 22 words starting from the word 'i', choosing each next word
randomly in proportion to its count raised to the power 1/temperature.

Generate 2 samples at temperature 0.2, 2 at temperature 1.0, and 2 at
temperature 2.0. Print them grouped under clear headings and wrapped
so I can read them.
```

**Why:** Read the three groups side by side. Low temperature gets stuck in loops (*the most humble and the most humble and…*); high temperature wanders off the subject entirely. This is the same dial you set on any commercial model — and it is why the same question can give you different answers.

<br>

### 5 · Count it properly

*Goes in: code cell*

```text
Count how many times each letter appears in the word 'strawberry',
and show how the tiktoken encoding `enc` splits that same word.
Print the two results side by side.
```

**Why:** Then ask the Colab AI chat panel the same question in words: *how many times does the letter r appear in strawberry?* Compare its answer to the count you just computed. Recent models often get this right — if yours does, ask it for a longer or rarer word and try again.

<br>

### 6 · Ask for citations in your own narrow specialism

*Goes in: AI chat panel*

```text
Give me five peer-reviewed articles about TOPIC, with the authors, the
title, the journal, the year, and the DOI for each.

  ^^^^^ replace TOPIC with the narrowest subject in your own research
        that you can state in one line, then delete this note
```

**Why:** If you paste it without replacing TOPIC, the model will ask you what topic you mean — which wastes a turn but does no harm.

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
- a list called `messages`, each entry a dict with a role
  (system, user, assistant) and text
- a function add(role, text) that appends to it
- a function show() that prints the whole transcript readably
- a function to_send() that prints exactly what would be sent to a
  model this turn, formatted as 'Role: text', with no banner or
  decoration around it
Start it with a system message and two example exchanges.
```

**Why:** Look carefully at what `to_send()` prints. That whole block is re-read from scratch by the model on every turn. Nothing is remembered; everything is resent.

<br>

### 2 · Count the tokens

*Goes in: code cell*

```text
Add a function called token_count() that returns the number of tokens in
the whole transcript, using tiktoken's 'cl100k_base' encoding.

Then add six more long exchanges to the transcript, printing the token
count after each one, and warn me whenever it goes over 600 tokens.
Finally plot the token count against the turn number, with a dashed
line at 600.
```

**Why:** The function name is pinned — a later cell calls `token_count()` by name. If your AI calls it something else, either rename it or tell the AI to.

<br>

### 3 · Add a reset

*Goes in: code cell*

```text
Add a function reset() that clears the transcript but keeps the system
message, printing the token count before and after. Then run it.
```

**Why:** Run this now. The next section asks you to copy the transcript by hand — and without a reset you would be pasting about five thousand characters of filler.

<br>

## Notebook 5 — The prompt tournament

### 0 · Look at the task first

*Goes in: code cell*

```text
Load dates_gold.csv into a dataframe called `gold` and show me all 20 rows
with the full letter text and the correct date, in a readable layout.
Count how many have no date at all.
```

<br>

### 5 · Score the versions

*Goes in: code cell*

```text
I have four strings called v1, v2, v3 and v4, each containing a model's
answers, one per line, in the form  L0213: 1685-05-09
IDs look like L0213. A missing year is written XXXX. An absent date is the
literal words NOT STATED.

Write code that pulls the ID and the date out of each line with a regular
expression, ignoring bold markers, table pipes, arrows, bullets and any
other text on the line, and compares them against the correct_date column
of `gold`. Treat a version with nothing pasted as 'not run' rather than 0%.

Show accuracy for each version as a bar chart and print every case where
version 4 was right and version 1 was wrong.
```

**Why:** Note what the prompt has to spell out: the ID shape, the XXXX convention, and the NOT STATED string. Without those three facts the AI writes a regex that silently drops a quarter of the answers — which is the whole lesson of this notebook, applied to itself.

<br>

## Notebook 6 — Question your own documents

### 1 · Extract, and check what you got

*Goes in: code cell*

```text
Install pypdf if it is not already available.

Read every PDF in the pdfs folder and every .txt file in the archive folder.
Build a dataframe called `docs` with one row per file and these columns:
filename, pages, chars, and text (the full extracted text).

If a file yields no text at all, record 'NO TEXT LAYER' for it and carry on
with the others - do not stop the whole run.
Show the filename, pages and chars columns sorted by chars ascending.
```

**Why:** **Read that table before going any further.** Sorting ascending puts the failures at the top where you cannot miss them. A file with 0 characters is invisible to everything that follows. Note the prompt asks for the text to be *kept* — a table of statistics with the text thrown away would leave section 2 with nothing to work on.

<br>

### 2 · Chunk, keeping provenance

*Goes in: code cell*

```text
Split the text of every document in `docs` into passages of about 120 words
with 30 words of overlap. Build a dataframe called `chunks` with columns:
n (a running number), file, part, and text.
Print how many passages there are, how many documents produced more than
one passage, and show the first two passages in full.
```

**Why:** Provenance is what makes a citation mean something later. Without it you get an answer with a number attached that you cannot trace back to anything.

<br>

### 3 · Build the search, and test it on its own

*Goes in: code cell*

```text
Turn every passage in `chunks` into a vector using TfidfVectorizer with
English stop words and bigrams, then TruncatedSVD with 100 components,
then normalise. Keep the fitted pipeline as `embedder` and the matrix as `V`.

Write a function search(question, k=5) that returns the k most similar
passages by cosine similarity, each with its similarity score, passage
number and source filename.

Test it with the question 'someone jailed with no accusation against them'
and print the results. Warn me if the best score is below 0.15.
```

**Why:** **Test retrieval before you connect it to anything.** If the search is bad, the answers will be confidently wrong and you will blame the wrong component.

<br>

### 5 · Build the prompt assembler

*Goes in: code cell*

```text
Write a function ask(question) that:
  1. retrieves the 5 most relevant passages using search()
  2. prints a warning if the best score is below 0.15
  3. prints a single block of text containing, in this order: the
     instruction below, the numbered passages each with its source
     filename, and then the question

The instruction must read:
  Answer using ONLY the passages below. After every statement, cite the
  passage number it came from, like [3]. If the passages do not contain
  the answer, reply exactly: 'The provided passages do not answer this.'
  Do not use anything you know from outside these passages.
```

**Why:** Notice that you are specifying the architecture of a retrieval system in plain English. That is the whole skill.

<br>

## Notebook 7 — Build your research agent (capstone)

### 2 · Build the tools

*Goes in: code cell*

```text
I want to build a supervised agent in this notebook.

The source files are the .txt files in the archive folder.
GOAL: for every file, produce one row with these columns:
   <PUT YOUR OWN COLUMNS HERE - from Step 1>

Build me four tools, each as its own function, each printing what it did:
  1. list_files()      - list the source files, print how many
  2. read_file(name)   - return its text, print the length
  3. make_prompt(text) - build an extraction prompt asking for the
                         columns above as a single JSON object, using
                         NOT STATED for anything the text does not say
  4. add_row(data)     - append to a results table, print the running count

Also give me a variable tracking which file we are on, so I can process
them one at a time and stay in control.

Do not process everything at once. Stop after each file.
```

**Why:** **Replace the columns line with your own before pasting.** If you leave the placeholder in, the AI will invent columns or ask you what you meant. The last two lines are the entire human-in-the-loop architecture, expressed as a requirement in plain English — you are specifying a system design without writing code.

<br>

### 4 · Make it attack the table

*Goes in: AI chat panel*

```text
Below is a table my extraction produced. List every way it might be wrong or
incomplete. Show me the three rows you are least confident about and say why.
Then name the specific kind of document that would break this extraction.

Do not defend the work. Only find problems.

TABLE:
<paste the table printed by the cell below>
```

**Why:** *Do not defend the work* is doing real work in that prompt. Without it, the trained-in agreeableness gives you reassurance instead of a review. Run the cell below first — it prints the table in a form you can paste.

<br>

### 5 · Save what you built

*Goes in: code cell*

```text
Save the `results` list as a CSV called agent_results.csv and download it
to my computer. Print how many rows were saved, and list any columns that
are entirely NOT STATED.
```

**Why:** The columns that are entirely NOT STATED are worth a thought: either the documents never contained that information, or your prompt asked the wrong question. Those are different problems with different fixes.

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
