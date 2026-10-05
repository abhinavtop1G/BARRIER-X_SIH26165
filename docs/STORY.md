# The Fatal Few: What We Learned Building BARRIER X

*Team GIT PUSH AND PRAY, Smart India Hackathon 2026, Problem Statement SIH26165 (Oil India Limited)*

---

## Twelve words

Picture a technician on an oilfield in Assam, opening a line on a compressor for routine maintenance.

The isolation valve wasn't double-blocked, and nobody tagged it out. There's pressure still sitting in a section of that pipe, and nobody on the crew knows.

This time it's fine. The pressure bleeds off through a fitting with a hiss that nobody will remember by the end of the shift. The job gets finished, the technician goes home, and before leaving, someone types a few lines into the near-miss system:

> "Technician entered the compressor area for line maintenance without verifying double-block isolation."

Twelve words. No injury, no damage, no investigation.

That report goes into a spreadsheet with thousands of others: a boot that slipped on a wet stair, a glove left on a handrail, a forklift parked across a walkway, a printer in the HSE office that ran out of toner. Every one of those was written by someone who cared enough to report it. Every one of them gets the same row height and the same place in the queue.

The compressor report is different, though, and if you've spent any time around safety people you'll know why. It describes an energy isolation failure, one of a small family of failures that sit behind a large share of the incidents that actually kill people. Next time a line gets opened like that, the pressure might not bleed off politely.

Nobody is going to read that report closely this week. That isn't carelessness. It's arithmetic. One HSE team, a few thousand rows, and a human brain that stops absorbing words after a few hundred of them.

That's the problem we ended up spending our hackathon on. It looks like a machine learning problem from the outside, but really it's a reading problem, where the cost of not reading is counted in people.

## The pyramid that lied to us

Most safety programmes still carry an idea from 1931. Herbert Heinrich drew a pyramid: lots of minor incidents at the bottom, fewer injuries above them, a few serious injuries above those, and a fatality at the tip. The intuition was that the layers move together. Shrink the base and the tip shrinks too.

For decades, that's how safety got managed. Count the small stuff, push the numbers down, celebrate the trend.

The small stuff did go down. Across industry after industry, minor injury rates fell.

Fatalities didn't fall with them, and that's the uncomfortable finding modern safety research keeps coming back to. Fewer than one in five incidents has the potential to cause a serious injury or fatality, and those incidents mostly don't come from the same causes as the minor ones. A slip on a wet floor and a worker crushed under a dropped load aren't the same event at two different sizes. One is about housekeeping. The other is about energy: something suspended, pressurised, electrical, or chemical that was supposed to be under control and wasn't.

You can mop every floor on a site and still lose someone to a parted sling the following week.

There's a term for the property that matters here: **SIF potential**, meaning whether an event *could* have caused a serious injury or fatality, regardless of what actually happened. A near miss where a load came down exactly where a rigger had been standing a minute earlier has huge SIF potential, even though nobody was touched. A painful, recordable paper cut has none.

What got to us, the more we read, was that the warning signs usually aren't hidden. Oilfield crews are trained to report. The near-miss systems are full. In a lot of serious incidents, someone had already written down the precursor, in plain language, weeks or months earlier.

The information exists. The time to read it doesn't.

## Why this problem

SIH 2026 had a long list of problem statements. Some had nicer data. Some had cleaner, more satisfying answers. A couple would have made much flashier demos.

SIH26165 asked for an AI/NLP engine to find serious injury and fatality precursors in Oil India's unsafe-act, unsafe-condition and near-miss reports. We kept drifting back to it, and when we talked about why, it always came down to the same thing: what's at stake here is real. Most software bugs cost money or patience. If this system ranks the wrong report low, the cost is somebody not coming home.

That's a scary thing to build for. It's also the most motivated any of us have ever been on a project.

We called it **BARRIER X**, after the barriers that safety engineering is organised around, the layers of protection between a hazard and a person. Pretty much every serious incident is a story of those barriers failing one after another. We wanted to catch them wearing thin before the last one went.

The team name, GIT PUSH AND PRAY, is exactly what it sounds like. Every hackathon team pushes code at 3 a.m. and hopes. We told ourselves that by the end, we'd have replaced the praying with tests. That part, at least, we managed.

## There is no dataset

We started out overconfident, like everyone does. The plan fit on a sticky note: get oil and gas incident reports labelled "could have been fatal" and "couldn't have", train a classifier, build a dashboard, done.

Then we went looking for the data, and there wasn't any.

No public dataset labels oil and gas narratives by SIF potential. India's incident portals are restricted to operators, which is fair enough. The big public incident collections we found record what *happened*: the injury, the damage, the outcome. Not what *could* have happened. That distinction sounds pedantic until you realise it's the whole problem. A model trained on outcomes learns to spot injuries. We needed one that spots potential.

We spent days on this. Regulator databases, academic corpora, Kaggle, government open-data portals. Every promising lead turned out to be outcome-labelled, or too short to be useful, or locked behind an account we couldn't get.

There's a particular quiet that settles over a team when the sticky-note plan dies. We sat in it for longer than we'd like to admit.

Eventually we found one dataset that actually fit: the **IHM Stefanini Industrial Safety and Health Analytics Database**, released publicly. Each row has a free-text incident description and a field called *Potential Accident Level*: the severity the incident could have reached, as judged by the safety professionals who filed it.

That's SIF potential, labelled by people who knew what they were looking at. We mapped levels IV to VI to "yes" and I to III to "no". No clever heuristics, just a documented mapping over a human judgement that already existed.

There were two catches. The data came from Brazilian mining and metals plants, not oil and gas. And it had **411 rows**.

That's it. As far as we could find, that's every publicly available SIF-potential label in the world.

We split it properly, grouped and stratified, with a check that no narrative appeared in two splits: 231 rows to train on, 57 to validate on, and 123 locked away in a test set that nothing would ever be tuned against.

So, 231 sentences to learn from. The severity scale was even thinner than that number suggests. The top level had exactly one example. The next level down had twenty-eight. Most of what any model could learn from this data was the line between level III and level IV.

You can't train a confident classifier on 231 sentences. We think anyone who claims otherwise is selling something.

## Ranking instead of judging

We could have pretended. Train something, report an accuracy number, put a green tick on a slide. Plenty of projects do.

What stopped us was thinking about the person at the other end: an HSE officer with a few thousand reports and one shift. What do they actually need from software?

Not a confident "SIF: YES". A wrong yes wastes their time. A wrong no is worse than having no system at all, because it buries a precursor under an official-looking label and teaches people to stop looking.

What they need is an order to read things in.

If someone can read twenty reports carefully in a shift, the most useful thing software can do is make sure those are the twenty most dangerous ones. It doesn't have to be perfect. It has to be clearly better than reading them in the order they arrived.

So BARRIER X became a ranker. Its whole job is to push the most dangerous reports to the top of a tired person's queue.

That changed what we measured. Accuracy mostly stopped mattering. The number we cared about was precision near the top: of the first ten reports we show someone, how many genuinely carry SIF potential? It changed how we'd present scores too, as calibrated probabilities and bands rather than verdicts. And honestly, it gave us permission to be upfront about the 411 rows, which turned out to matter more than anything.

## Losing to word counts

Every serious ML project needs a boring control, the simplest thing that might work. If your model can't beat it, your model isn't doing anything.

Ours was TF-IDF with logistic regression: count the words, weight the rare ones, draw a line. You can explain it on a whiteboard in two minutes.

We expected to beat it easily. It scored a PR-AUC of 0.653 on the frozen test set, against a base rate of 0.407.

Then we fine-tuned a standard transformer on the same 231 rows, and it lost: 0.629. A modern deep learning model, built by people who'd read the papers, beaten by word counts.

We tried the obvious fix and pooled in more incident data. The word-count model got worse, not better: 0.638.

That was a rough week. We'd picked this problem believing modern NLP could do something meaningful with it, and the data kept telling us a whiteboard model was just as good.

Underneath the frustration, though, we understood why. Word counts don't understand anything. They see "pressure", "valve" and "line" without knowing whether the pressure was isolated. They see "fell" without knowing if it was a pen or a person. And they learn the surface vocabulary of whatever they're trained on. Our labels were Brazilian mining prose and our target was Indian oilfield reports. A model that had memorised mining vocabulary could do fine on a mining test set and fall over the moment it read a wellsite narrative from Assam.

We didn't actually need a model that did better on 123 mining sentences. We needed one whose judgement survived the move to a different industry. At that point we didn't even have a way to measure that.

## Why we didn't just use an LLM

It's 2026, and the shortcut is sitting right there on everyone's screen: paste the narrative into a big language model and ask whether it could have killed someone.

It's tempting, and the answers look impressive: instant, fluent, a paragraph of reasoning that sounds like a consultant wrote it.

But the weaknesses are well known, and they're exactly the wrong ones for this job. A generative model can give different answers to the same question. A small change in wording can flip its verdict. And it can cite a rule or a standard that doesn't say what it claims, with complete confidence.

In a chat app, a confidently wrong answer is mildly annoying. In a safety queue, it's an unisolated pressure line ranked below a printer jam, delivered so smoothly that nobody thinks to question it.

So we wrote down what the thing at the centre of the queue had to be. It had to give the same report the same score every time. It had to be measurable on a test set. Its numbers had to mean something, so a threshold would mean something. Months later, someone had to be able to ask "why wasn't this flagged?" and get a real answer, including exactly which model produced the score. And it had to run where the reports are, on ordinary hardware, not only where the GPUs are.

A language model used as the scorer failed every one of those. So we set a rule for the rest of the project: the model that decides the order is small, measured and deterministic. Language models can help explain things later. They never decide what a human sees first.

That meant taking the hard road and making a small model genuinely good with almost no labels.

## The 0.70 that meant nothing

This is the part most project write-ups leave out, so we're going to spend some time on it.

A few weeks in, our pipeline posted a PR-AUC of 0.70 on the frozen test set. Better than the baseline, better than the plain transformer. We were pleased with ourselves for roughly a day.

Then we did the thing that ended up saving the project: we stopped staring at the test set and tested the actual deployment domain.

We wrote six realistic, severe oil and gas narratives: a suspended load, H2S exposure, contact with a live high-voltage line, an unpermitted confined-space entry, a scaffold collapse, and a high-pressure gas ignition. We wrote six obviously trivial ones: a coffee spill, a flickering bulb, a printer out of toner. And one control string, just a run of repeated letters with no meaning at all.

We ran them through the full serving stack: the real API, the real model files, the real thresholds.

It flagged none of the six severe narratives. The severe ones averaged 0.507 and the trivial ones averaged 0.500, a gap of seven thousandths. The string of repeated letters scored 0.521. Gibberish ranked above an H2S exposure, above a man standing under a falling load, above every real severe narrative we wrote.

Nobody said much for a while after that run.

A model that looked good on paper was useless in practice, and arguably worse than useless, because the dashboard looked confident. So we took it apart, and over the next several days we found nine separate defects. None of them showed up in the metric we'd been proudly watching.

The classifier's final layer had barely trained and was still sitting close to its random starting point, so every probability landed between 0.494 and 0.581. There was no calibration, so the outputs had no reason to behave like probabilities and any threshold was arbitrary. The ONNX export, the fast format we'd built for deployment, was completely dead: it returned 0.533 for every input, a ROC-AUC of exactly 0.5000 (a coin flip), and the export command exited without a single error. Five of our six saved checkpoints wouldn't even load, because the library version that wrote them disagreed with the one serving them about how one tokenizer field was stored.

It kept going. Two of our four risk bands were mathematically unreachable. The band edges sat 0.15 either side of the threshold, but the scores only spanned 0.06, so "HIGH" needed at least 0.667 when the model never went above 0.556. Every report came out ELEVATED or BORDERLINE, whatever it said. The threshold was being matched to the model by sorting filenames, and it was only correct because one file happened to sort last. The probability calibrator diverged on our validation data, and the fallback logic quietly shipped no calibration at all. Our export quality check only asked whether PR-AUC dropped, which let a compressed model through even though it had reshuffled the ranking.

The ninth one was found by CI, on its very first run. If the model file was missing, the service crash-looped forever instead of starting in a degraded state, because an exception type slipped past the error handler. None of our laptops ever hit it, because all of them had the model on disk. CI was the first environment that didn't.

Each of those was small, and each one was invisible to the number we trusted. Together, they turned a promising model into a system that ranked gibberish above a fatality.

The lesson we took from it is simple: a good test-set number doesn't mean you have a working safety system.

It cost us days we didn't have. It also gave us something that's still there: a selftest script with one end-to-end check for every one of those nine defects, which now runs on every push to the repository. If any of them ever comes back, the build fails before anyone sees a wrong score. It changed how we worked, too. After that, nothing was done just because a number went up. It was done when we could explain why the number moved and show the system behaving sensibly on text it had never seen.

## Getting signal without labels

Fixing bugs didn't change the core problem. We still had 231 training rows, and we couldn't produce new SIF labels. Doing that properly takes trained safety professionals, and we had neither the people nor the weeks.

So the question became: what can a model learn from data that's real, public and close to our domain, even if nobody labelled it for our task?

We ended up with two answers, and they taught the model different things.

### Learning the vocabulary

The first was sheer volume. We gathered 589,717 unlabelled safety narratives, about 154 MB of text, from NIOSH injury narratives, OSHA construction abstracts and PHMSA hazmat incident reports. Before writing any of it to disk, we removed 185 narratives that overlapped with our held-out evaluation data, matched by hash, so nothing could leak into the test.

None of that text had SIF labels, and it didn't need them. We used masked language modelling: hide a word, make the model guess it from context, and repeat that a few hundred thousand times. The text is its own answer key. A pretrained model has read billions of words of general text, but it's barely seen "LOTO", "permit to work", "banksman" or "line of fire" used the way a safety officer uses them. This stage fixes that before a single label gets spent.

We picked DeBERTa-v3-small: modern, good at context, and small enough to run on a CPU. There was a wrinkle we had to watch. DeBERTa-v3 was originally pretrained with a different objective, so its masked-word head starts from scratch, and we kept a close eye on the first couple of thousand steps in case it stalled. It didn't. Over 15,000 steps the loss fell from 1.995 to 1.556, and perplexity dropped from 7.36 to 4.74. In plain terms, it got a lot better at predicting the words safety narratives actually use.

It also helped where we cared. The adapted model reached a PR-AUC of about 0.69 on the frozen test set, against 0.63 for the same model without adaptation, and we checked that across 0, 5,000 and 15,000 steps to make sure the gain grew with training rather than coming from a lucky seed.

### The dead end

Our first idea for the next stage was a NIOSH dataset that came with 63,272 free rule labels. It looked like a gift: big, labelled, public, safety-related.

It made things worse. Trained on those labels alone, the model scored at chance. Pooled with our own data, it dropped well below the baseline. Eleven thousand extra labelled rows, and performance went down.

It took us a while to work out why. NIOSH narratives average 86 characters of hospital-triage shorthand. Ours average 363 characters of field prose. The topic matched, but the way the text was written didn't, and the model was learning to read one register and getting tested on another. That turned out to be the most useful lesson of the whole project: for transfer, how the text is written matters as much as what it's about.

### Learning what severity means

So we went looking for real severity judgements written in roughly the same way as our reports, and found them in the US Department of Transportation's PHMSA hazmat incident reports: 655 monthly files spanning more than fifty years, 395,481 usable narratives.

Each of those reports has a "serious incident" indicator, a regulatory determination by whoever filed it that the incident met a serious-incident criterion, such as a fatality, a major injury, an evacuation, or a major release. That's a human severity judgement over free text, which is structurally our task on a different substrate. And the narratives average 336 characters, almost exactly the register of ours.

Before spending any GPU time we checked the signal was real. A simple word-count model trained only on PHMSA, with no mining data at all, reached a PR-AUC of 0.575 on our test set. That's weaker than training in-domain, but clearly above the base rate, which is exactly what you want from an intermediate task.

We trained on 72,990 of those reports, sampling four non-serious ones for every serious one, since only 3.69% were serious. The technique is called STILT, Supplementary Training on Intermediate Labeled-data Tasks. On held-out PHMSA data, the model reached a PR-AUC of 0.916 and a ROC-AUC of 0.973. It had learned to recognise severity in a real regulatory sense, and we hadn't written a single new label.

## Four rounds of training

By the end, the model had been trained four times, each round starting from what the previous one left behind. Microsoft's pretraining gave it general language. The 590K narratives gave it the vocabulary of industrial hazard. The PHMSA reports taught it what a severity judgement looks like. Only then did it see our 231 rows and learn the actual task.

One detail at the end mattered more than we expected. The PHMSA stage leaves the model with a classification head tuned to PHMSA's world, where about one in five sampled examples is serious, while our base rate is around 41%. Keeping that head scored worse. So in the last stage we threw it away, trained a fresh head, and gave it twenty times the learning rate of the rest of the network, so it could catch up without disturbing what the rest of the model had learned.

We didn't guess our way there. We tried the intermediate stage several ways, keeping the head or resetting it at different learning rates, with three seeds each, and we kept a record of the variants that failed as well as the one that worked. Resetting the head at the normal learning rate was clearly worse. A higher head learning rate helped the plain model and hurt the adapted one. Only the combination we shipped held up.

## What actually improved, and what didn't

The obvious question is whether all of that helped.

On the frozen 123-row test set, the PHMSA-trained model scored a little higher than the adapted model without it. That would have been easy to put on a slide. Instead we ran a paired bootstrap, resampling the test set 5,000 times and comparing models on the same resampled rows each time. The improvement came out at +0.0245 PR-AUC, with a 95% confidence interval from −0.070 to +0.122.

That interval contains zero, so we don't claim the improvement. On 123 rows, differences under roughly 0.10 PR-AUC can't be resolved. That's a property of the test set, not of any model, and the same analysis shows the gap between our final model and the TF-IDF baseline isn't resolvable either. We committed the raw per-seed scores and calibrators to the repository, about 61 KB in total, so anyone can rerun that bootstrap on a laptop in seconds and get the same numbers. We checked that before we deleted 14.6 GB of intermediate checkpoints, not after.

### Where it did change everything

The question we actually cared about was never whether the model did better on Brazilian mining text. It was whether its judgement survived the trip to an oilfield.

So we went back to the hand-written oil and gas probes (six severe, six trivial, one gibberish control) and ran every seed of every model family through them, with nothing filtered out.

Every model trained without the PHMSA stage ranked the string of repeated letters above every real narrative. Severe or trivial, H2S exposure or coffee spill, the gibberish beat all twelve.

Every model trained with it separated severe from trivial perfectly, with a ROC-AUC of 1.000 on every seed, and the gap between severe and trivial scores was about five times wider.

That's the result that justified the whole design, and you can't see it in any in-domain metric. Without severity training, the model had learned the surface texture of Brazilian mining prose. With it, the model had learned something about danger that carried across industries.

We want to be careful here. Twelve hand-written probes are an indication, not a benchmark, and six obvious catastrophes against six obvious non-events is an easy contrast. What makes it worth acting on is that nine out of nine seeds behaved exactly according to their family. A real evaluation needs real Oil India narratives, which we haven't had.

### The harder test, and where it still fails

Because those probes were too easy, we wrote a harder set of fifteen. It leads with near misses where nobody was hurt but somebody could have died, since that's the whole idea of SIF potential. It includes real injuries with low potential, which a naive model would over-rank, and a narrative from a workover at Duliajan, because that's where this system is meant to be used.

The served model got a ROC-AUC of 0.926 on that set, and all five of its top five picks were genuine high-potential events. The ranking held up.

The threshold didn't. A scaffold plank slipping at eight metres scored 0.299 and wasn't flagged. A travelling block that came down while two crew were underneath it, a potential double fatality, scored 0.295 and wasn't flagged. A printer running out of toner in the HSE office scored 0.331 and was.

That one stung. It's our own probe set; nobody would have known if we'd left it out. But a team building a safety system that hides its own failures is building exactly the kind of false confidence this project exists to fight.

So we dug in. The threshold, 0.3027, was fitted on Brazilian mining validation data. In that domain it behaves fine. Out of domain, the model's absolute scores drift, but its ordering mostly survives. The same probes turned up two more uncomfortable things. Adding "A fatality occurred" to a budget-meeting note actually lowered its score, which tells us the model isn't keyword matching, but also isn't fully reading meaning on text far from its training data. And rewording the same incident moved its score by about ±0.12, which is roughly the size of the whole gap between the two classes.

That's why BARRIER X flags by rank. On those fifteen reports, the absolute threshold got 0.78 precision, while taking the top five by rank got 1.00. The batch endpoint has a `top_frac` option for exactly this case: flag the most dangerous slice of whatever came in, however the absolute scores have drifted. The ranking transfers and the threshold doesn't, so the product ranks.

### The numbers we'll stand behind

We picked the served model by its validation score, never its test score. That meant shipping a seed that wasn't the best on test (0.667 against 0.709 for a sibling), and we think that gap is simply the cost of not cheating.

On the 123 held-out reports, with a base rate of 0.407, it gets a ROC-AUC of 0.757 and a PR-AUC of 0.667. Precision at 10 is 0.80: eight of the first ten reports a reviewer reads are genuine SIF precursors, about twice as good as reading them in arrival order. Recall at the threshold is 0.86 in-domain. Each report takes 46 milliseconds on a CPU.

## Making the scores mean something

A score of 0.42 is useless if nobody knows what 0.42 means.

The raw model was saturated. It pushed scores toward 0 and 1, saying "certain" when the honest answer was "maybe". On validation, its stated confidence was off by about forty percentage points on average.

We fixed that with Platt scaling, a two-parameter curve fitted on the 57-row validation split, never on test. Two parameters on purpose: anything more flexible would just fit noise at that size. Our code supports other calibrators, but it deliberately refuses to use them on a validation set this small.

The first version of the fitter blew up. The optimiser underneath went numerically unstable on nearly separable data and overshot. Adding a backtracking line search, which shrinks each step until it actually improves things, fixed it.

Because the calibration curve only ever goes up, it can't change the order of reports; we checked to six decimal places that the ranking metrics didn't move. What it changes is what the numbers mean. Calibration error on validation dropped from 0.402 to 0.084. Scores now span a realistic 0.205 to 0.596 instead of slamming into 0 and 1, and all four risk bands actually get used on real data rather than two. The band edges aren't hard-coded any more either. They're derived from the calibrated validation data, 0.0477 either side of the threshold for the served model, and stored next to it.

So when BARRIER X labels a report HIGH, ELEVATED, BORDERLINE or LOW, those words correspond to measured positions around an operating point chosen on validation data, rather than a vibe.

## Building for places with bad Wi-Fi

An oil rig isn't a data centre. The connection is thin, there are no GPUs, and IT support might be a long drive away. If the system needs the cloud to think, it fails exactly where it's needed most.

The model runs on ONNX Runtime, a small inference engine, and we took PyTorch out of the serving image entirely, which saves around 800 MB. The Dockerfile checks this at build time, so a future dependency change can't quietly bloat the image or break it on its first request.

Remember the dead export that returned 0.533 for everything? The new one is checked against the original model on the whole frozen test set. The full-precision export is numerically identical, with a maximum difference of 0.000008 and identical ranking, and it runs at 46 milliseconds per report on an ordinary CPU.

We also turned down an easy win here. A compressed int8 version was a third of the size, about a third faster, and scored a higher PR-AUC on the test set. We rejected it, because its rank correlation with the full model was only 0.77. Compression had reshuffled the queue, and on 123 rows a reshuffle can land favourably by luck. Our old one-sided check would have let it through. The new one requires a rank correlation of at least 0.95, deletes the compressed model if it fails, and serves the full-precision one instead. For a ranking product, a model that shuffles the queue is worse than a slower one that doesn't.

Getting the model onto a machine had its own lessons. The serving bundle is 531 MB, too big to live in the repository, so it ships as a GitHub release. One command downloads it, checks its SHA-256 hash, and extracts it with a guard against unsafe paths. It tries three download methods in turn: the GitHub CLI, then curl, then plain Python. That wasn't overengineering. On the machine we built this on, TLS interception broke one method halfway through a download while the other two worked, and inside CI a different method timed out. Any single method would have failed somewhere, and remote sites have exactly that kind of network.

The production container bakes the model in, so at runtime it doesn't need a network connection at all. CI builds it, starts it, scores a narrative through it, and compares the result against the development machine: same fingerprint, same score, every run.

### Reports the way people actually write them

Real field reports in India aren't written in textbook English. They mix Hindi and English, slip into Assamese, abbreviate everything, and are full of typos from tired people typing with gloves on.

So BARRIER X normalises each report before scoring it. It transliterates Devanagari and Assamese script, expands oilfield abbreviations like H2S and SCBA, maps romanised Hindi and Assamese words (*majdoor*, *machan*, *gir gaya*) to English, and fixes typos against a domain lexicon.

Rewriting someone's input can hurt as easily as help, so we measured it. We wrote ten incidents twice each, once in clean English and once the way they'd really come in from a rig, and checked whether the messy version scored like its clean twin. Typos came back exactly, which is the sanity check. Abbreviations nearly closed the gap. Hinglish closed most of it. Agreement with the clean ranking went from 0.27 to 0.62.

It wasn't all good news. Assamese barely improved: the word for "fell" transliterated correctly, then found no entry in our glossary. The fix is a lexicon entry, but we deliberately didn't tune the lexicon against our own test, because a glossary edited until its test passes doesn't measure anything. One mixed-language example actually got worse, and three of the ten pairs moved the wrong way overall, so normalisation isn't free. Across just ten pairs, the average improvement's confidence interval still includes zero. What would settle it is a few hundred real Oil India reports with the original text preserved, which is maybe half a day of work once those reports exist.

## Seeing the pattern across a site

A single report is the right unit for triage, but it's the wrong unit for prevention.

Serious incidents are rarely preceded by one alarming report. More often there are several boring ones: a scaffold plank that shifted underfoot, a hot-work permit nobody signed, a gas test skipped because the meter was in the other truck. A per-report model correctly scores each of those as unremarkable, and a reviewer correctly closes each one. Nobody notices that they all happened on the same rig in the same month.

So we built site-level risk. Any scored report can be recorded against its site in an append-only history, because you can't spot a pattern in reports you've already thrown away. Then each site gets assessed in four steps. Each report's weight halves every 30 days, since unsafe conditions get fixed and old reports are weaker evidence that a hazard is still live. Reports describing the same hazard are grouped together, using shared Life-Saving Rules and shared wording. Repeated reports of the same hazard add weight, but on a logarithmic curve, because five reports of one loose plank are one hazard plus evidence that nobody's fixing it, not five hazards. Finally, distinct hazard groups are combined with noisy-OR, since separate hazards are separate paths to harm.

The arithmetic is deliberately simple. Take three dull hazard groups at 0.35 each. None of them crosses the 0.50 review line, but together, 1 − (1 − 0.35)³ comes to 0.725. The site crosses the line, and BARRIER X raises a compounding alert: no single report reached review, but three hazard groups are live at once, and together they do.

We hold this part to the same standard as everything else. There's no labelled test set behind it, because no public dataset connects near-miss logs to what later happened at those sites. Noisy-OR assumes hazards are independent, and hazards that share a crew and a supervisor aren't, so it overstates. It also inherits the per-report model's out-of-domain mistakes. In our own demo, three toner-cartridge reports nudge an office up to a watch level. So we built it to be argued with: every constant is visible in every result, and every alert comes with the exact reports and phrases behind it. The person reading it should look at the evidence, not just the number.

## The rest of the system

A model on its own isn't a product. The product is what a tired person sees when they open it at the end of a shift.

BARRIER X runs as five services, started with one `docker compose up`.

The **React frontend** is where HSE officers actually work. They sign in, see an overview, browse reports, and on the SIF Analysis page they can drop in the week's CSV, watch the columns get detected, watch each row get scored with a progress bar, and export the ranked list in one click. The same batch can go to the agent for questions. For hackathon judges, there's also a demo login that skips Google sign-in, which only works when the gateway is explicitly configured to allow it.

The **Go gateway** sits in front of everything. Every request goes through CORS, logging and authentication checks. Google sign-ins are verified on the server against Google itself, and the gateway then issues its own signed session, so nobody can get in by editing a token in their browser. It forwards scoring requests to the ML service and saves the results to MongoDB. If the ML service goes down mid-shift, the gateway doesn't fall over with it. It returns clearly labelled fallback guidance, and its health check reports exactly what's wrong.

The **ML service** serves single reports, batches with the `top_frac` option, the site risk ranking, and a self-contained dashboard that works with no build step and no internet connection. We tried to build it like something a real team would have to run. Every prediction writes one audit line with the score, the threshold, the band, the decision, how long it took, and a content fingerprint of the exact model weights, so that months later someone can find out precisely which model produced a score. Report text is hashed rather than stored in that audit log by default, because incident reports name real people, and audit logs tend to be kept longer and read more widely than the reports themselves. There are API keys, a per-caller rate limit, request IDs that follow a call through the system, and IOGP Life-Saving Rule matching on every report: which rules the wording touches, which phrases triggered each match, and what the reviewer should check.

Then there's the agent, and **MongoDB** for users and reports, with an in-memory fallback so a missing database never takes the gateway down.

## An agent that has to show its work

Given everything above, building an AI agent felt a bit contradictory. We did it anyway, because HSE officers have questions a ranked list can't answer. Which compressor has had the most isolation problems this quarter? What do this week's uploaded reports say about scaffolding? What does the confined-space rule actually require?

So we gave the language model a narrow job. When a question comes in, an intent router picks the tools to run: searching the safety reports, assessing a specific asset, summarising site risk, or reading the reports uploaded in that session. Those tools pull real records first. Only then does a language model see the question along with what was retrieved, and it's instructed to cite Report IDs and IOGP Life-Saving Rules, so its answers point back to documents a person can open and check.

If the main model isn't available, the agent falls back from Gemini 2.5 Flash to Groq's Llama 3.3 70B, then to OpenAI, and finally to a built-in base of HSE guidance, so it never just goes silent. The API keys stay on the server.

That's our answer to the temptation from the beginning. The language model explains; it doesn't score. The ranking that decides what a person sees first stays deterministic and auditable.

We should be clear about one limit. Right now the agent is told to cite its sources, but nothing automatically checks those citations before an answer is shown. Building that check is high on our list, which is the next section. Until then, the officer reads the answer, opens the cited reports, and makes the call. That's how it should work anyway.

## Tests instead of prayers

We named the team after a joke about hoping the build works, then spent a lot of the project making sure we'd never have to hope.

Every push to the repository runs five CI jobs. Unit tests run on two Python versions, covering the HTTP contract, security, calibration, the audit trail, site clustering and ingestion; 157 of them run without the model at all. An integration job downloads the real model release, checks its hash, runs the selftest (one check per defect we found), then starts the service and scores a real narrative. A Docker job builds the production image, confirms PyTorch isn't in it, starts it, and requires an H2S narrative to land in the HIGH band. The last job builds the gateway, agent and frontend images and tests each one, including the gateway's reporting when the ML service is unreachable and the demo login behaving correctly whether it's switched on or off.

Several of those tests exist only so that mistakes we already made can't come back. One of them checks that calibration leaves the ranking metrics exactly unchanged. If that ever fails, every number in this article quietly stops meaning what it says, and we'd rather the build tell us than a judge.

## A shift with and without it

Think about the HSE officer as things are now. It's late in the week. A spreadsheet with a few thousand rows is open on one screen, a deadline on the other. Somewhere in there, they have a nagging feeling that something matters, an instinct built over years, but not the hours to find it. They start reading carefully, then faster, then skimming. By row four hundred the words have stopped landing. That isn't a failure of effort. It's what happens to anyone asked to do that.

Now picture the same week with BARRIER X. They upload the CSV, the columns are detected, and a progress bar fills while each report is scored, banded and matched against the Life-Saving Rules. At the top of the queue, marked HIGH, is a twelve-word near miss about compressor maintenance without verified isolation, with the matching phrases highlighted under Energy Isolation. Just below it is a site alert: three hazard groups active at one rig (working at height, work authorisation, hot work), none of which reached review alone, but which together do.

They ask the agent which other reports mention that compressor, and it lists them with their IDs. They export the ranked list, close the laptop, and go out to the site. Before that line is opened again, someone checks the isolation. Before the next lift on that rig, someone checks the scaffolding and the permits.

And then nothing happens. Nobody files a report about the fatality that didn't occur, and there's no news story about the crew that went home on time. In this line of work, success mostly looks like a Tuesday that stayed ordinary.

That's what we're aiming for. Not replacing the safety officer, whose judgement no model is going to match, but protecting their time so that judgement lands on the reports that could kill someone. Less time ploughing through spreadsheets in arrival order, more time in the field acting on the reports that matter most.

## Where we want to take it next

The hackathon gave us a working foundation. It also gave us a clear list of what we haven't done yet, and this is roughly the order we'd tackle it in.

**Getting real reports.** Everything depends on this. We've never scored a genuine Oil India report; every label came from Brazilian mining and every oil and gas test used narratives we wrote ourselves. The first thing we'd want is a pilot with a few hundred historical reports, anonymised however Oil India's HSE team needs, scored side by side with their existing review. That would tell us how well the ranking really transfers, give us a properly fitted threshold for Indian oilfield text, and settle the normalisation question we couldn't answer with ten hand-written pairs.

**Learning from reviewers.** Once BARRIER X sits in a real workflow, every decision a reviewer makes becomes a label. When someone opens a HIGH report and closes it as harmless, or digs a dangerous one out of the BORDERLINE band, that's exactly the expert judgement we couldn't get for our training set. We'd like to capture those decisions, with the reviewer's agreement, and use them for periodic retraining, prioritising the reports the model is least sure about so every hour of expert review teaches it as much as possible. Even a few hundred labelled Oil India reports would probably matter more than any architecture change we could make.

**Checking the agent's citations.** We want every Report ID and rule the agent cites to be checked against the database before an answer is displayed, with anything unverifiable removed or clearly marked. It's not glamorous work, but it's what makes the agent safe to rely on.

**Doing Assamese properly.** Our normalisation works reasonably for Hinglish and badly for Assamese, and the fix isn't clever modelling. It's sitting with people who actually write these reports in the field, building the vocabulary they use, and testing on reports we didn't write ourselves.

**A real Life-Saving Rules classifier.** Today's rule matching is deliberately simple and transparent. Next, we'd transcribe the rules properly from the IOGP reference documents and train a multi-label classifier, so a report that describes a hazard without using the obvious words still gets mapped to the right rule.

**Validating site risk.** The compounding alert is the part we find most exciting and the part we can least prove. With historical data that links near-miss reports at a site to what later happened there, we could finally test whether compounding sites really do go on to have more serious incidents, and tune the decay and clustering on evidence instead of judgement.

**Getting closer to the field.** We'd like supervisors to be able to file and check reports from a phone, even with no signal, syncing when they're back in range, and to run the scoring model on a site-office laptop with no cloud dependency at all. The model already runs on a CPU in 46 milliseconds. Further out, we're interested in streaming reports in as they're filed instead of in weekly batches, and in generating audit reports in the formats Indian regulators like OISD and DGMS expect.

**Revisiting a smaller model.** We rejected the compressed int8 version because it reshuffled the queue. We think part of the reason is that the model is overconfident, and a better-calibrated model might compress more cleanly. A model a third of the size would make offline deployment on modest hardware much easier, so it's worth another try, held to the same rank-correlation bar as before.

The frontend already has placeholders for a few of these: precursor pattern detection, Life-Saving Rule mapping, and a 3D view of risk across a facility. They're placeholders on purpose. We'd rather show an honest "coming soon" than a demo that pretends.

None of this will be quick, and most of it depends on working closely with the people who do this job every day. That's the part we're most looking forward to.

## Why it matters to us

Every hackathon project has a moment where it stops being an assignment and starts feeling like yours.

For us, it was the night the gibberish string outscored the H2S narrative. We'd been proud of a number, and a meaningless run of letters showed us the number was hollow. If we'd shipped that version, a dashboard would have told a safety officer, with total confidence, that nothing in their queue was dangerous.

After that, the project wasn't really about winning a hackathon any more. It was about building something we'd trust if the person opening that compressor line was someone we cared about: something that's honest about what it knows and what it doesn't, that's tested on every push so a mistake we made once can't sneak back, and that runs on an ordinary laptop in a site office with bad Wi-Fi, because that's where the reports are.

We're a student team, and we're not going to pretend BARRIER X is finished or that it can replace the people who keep oilfields safe. What we have is a careful, working foundation, and some evidence that you don't need a giant model or a perfect dataset to make a real difference. You need the right question, a willingness to measure everything, and the stomach to publish the numbers that disappoint you.

Every incident report is a warning someone took the time to write down. Most of them never get read closely, not because nobody cares, but because there are too many and not enough hours.

The fatal few are usually already written down. We'd like to make sure someone reads them first.

*Team GIT PUSH AND PRAY · BARRIER X · Smart India Hackathon 2026 · SIH26165*
