# Learning science for study sites

What the research says makes people remember and use what they study, turned into checks for a study site or a question bank. `learning-experience.md` covers the interface of a study site. This file covers whether it teaches.

Use it when a request is about learning, exams, questions, lessons or flashcards. `python <standard>/scripts/learning_check.py <folder>` checks a question bank against the rules below that a program can check.

## What works, in order of evidence

Dunlosky and colleagues (2013) rated ten study techniques by the evidence behind them. Two had high utility: practice testing and distributed practice. Interleaving and elaborative questioning had moderate utility. Highlighting, rereading and summarizing had low utility.

| Practice | What the site does | How to check it |
| --- | --- | --- |
| Retrieval practice | Asks the learner to answer from memory before showing the content again. A question comes before the summary, not only after | A lesson ends with questions answered without the text on screen |
| Spacing | Brings a topic back after days, more often for what the learner missed | The site keeps the date of each answer and offers a review of due items |
| Interleaving | Mixes questions of several topics in one practice session once each topic was seen | A practice mode draws from more than one topic. Every question names its topic |
| Feedback that explains | After an answer, says why the right option is right and why the chosen wrong option is wrong | Every question has an explanation and every wrong option its own reason |
| Worked examples, then faded | Shows a solved case step by step, then a case with steps missing, then a case to solve alone | Labs and exercises go from complete to partial to blank |
| Two channels | Pairs a diagram with words that explain it, close to each other, and removes decoration that carries no meaning | Every diagram has its explanation next to it and alt text that says what it shows |
| Small steps | One idea per block, the vocabulary first, then the idea | Long lessons are split, and the terms come with a definition at first use |
| Know what you know | Asks how sure the learner is before showing the answer, so wrong and sure answers come back first | An optional confidence choice is stored with the answer |

## Questions that teach and measure

From the review of item writing guidelines by Haladyna, Downing and Rodriguez (2002):

- Three or more plausible options. Distractors come from real mistakes, not from jokes or filler.
- Options of similar length and grammar. When the key is often the longest option, length gives it away.
- The key in every position about equally often, unless the page shuffles the options. `learning_check.py` reads the code of the repository to see whether it does.
- No "all of the above". "None of the above" only rarely.
- A stem that asks a full question. Avoid negatives. When one is needed, write NOT or EXCEPT in capitals.
- One question once. The same stem under two ids splits the learner's history.

## What to measure

A site helps learning when learners recall more later, not when a page looks good. Before claiming it:

1. Keep the answers of each learner with the date, the question id and the topic, on the device.
2. Compare the first try at a question with a later try at the same question, days later.
3. Run the comprehension test of `writing-and-usability.md` with five learners of the audience on one lesson.

Report what was measured and with how many people. Never report a learning gain the data does not show.

## Sources

- Dunlosky, Rawson, Marsh, Nathan and Willingham (2013), Improving students' learning with effective learning techniques: https://doi.org/10.1177/1529100612453266
- Roediger and Karpicke (2006), Test-enhanced learning: https://doi.org/10.1111/j.1467-9280.2006.01693.x
- Cepeda, Pashler, Vul, Wixted and Rohrer (2006), Distributed practice in verbal recall tasks: https://doi.org/10.1037/0033-2909.132.3.354
- Rohrer and Taylor (2007), The shuffling of mathematics problems improves learning: https://doi.org/10.1007/s11251-007-9015-8
- Hattie and Timperley (2007), The power of feedback: https://doi.org/10.3102/003465430298487
- Butler and Roediger (2008), Feedback enhances the positive effects and reduces the negative effects of multiple-choice testing: https://doi.org/10.3758/MC.36.3.604
- Sweller, van Merriënboer and Paas (2019), Cognitive architecture and instructional design, 20 years later: https://doi.org/10.1007/s10648-019-09465-5
- Mayer and Moreno (2003), Nine ways to reduce cognitive load in multimedia learning: https://doi.org/10.1207/S15326985EP3801_6
- Haladyna, Downing and Rodriguez (2002), A review of multiple-choice item-writing guidelines: https://doi.org/10.1207/S15324818AME1503_5
