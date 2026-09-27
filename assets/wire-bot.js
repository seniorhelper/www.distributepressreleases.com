/* Wire — wire-desk assistant for Distribute Press Releases.
   Rule-based. No model, no key, no network call. Injects its own markup.
   Rule: never state a guarantee, never invent a fact, always offer a human. */
(function () {
  "use strict";
  if (document.getElementById("dpr-bot")) return;

  var CONTACT = "the contact page (/contact/)";

  /* ----- knowledge ----- */
  var K = [
    { id: "greet",
      k: ["hi","hello","hey","yo","howdy","hiya","sup","good morning","good afternoon","good evening","greetings","anyone there","you there","hey there","wassup","whats up","what's up"],
      a: [
        "Hey. I run the wire desk here. What are you working on \u2014 an announcement, or figuring out whether you need one?",
        "Hi there. Ask me anything about distribution, pricing, or the free tools. Where do you want to start?",
        "Hello. I can help with what a release does, what it costs, and what it will not do. What brought you in?"
      ] },
    { id: "howareyou",
      k: ["how are you","how r u","how you doing","hows it going","how's it going","you good","how are things"],
      a: ["Running fine, thanks. What can I help you sort out?"] },
    { id: "price",
      k: ["price","pricing","cost","how much","much","rates","rate","fee","fees","charge","expensive","cheap","budget","afford","quote","what do you charge","ballpark"],
      a: ["A single release is $99, everything included \u2014 no per-word or per-image add-ons. Monthly is $89 a month for one release a month. Annual is $890 for twelve, which works out to about $74 each. Full breakdown is on the <a href=\"/pricing/\">pricing page</a>. Which fits how often you'd publish?"] },
    { id: "annual",
      k: ["annual","yearly","discount","cheaper","save","subscription","monthly plan","per year"],
      a: ["The annual plan is $890 for twelve releases \u2014 two months free compared with paying monthly. Cadence is the reason it exists: AI answer engines rebuild their citation sets on roughly a four-week cycle, so a steady drip tends to matter more than one big send. Want the <a href=\"/pricing/\">plan comparison</a>?"] },
    { id: "whatsincluded",
      k: ["what do i get","whats included","what's included","included","deliverable","package","what comes with"],
      a: ["Every release ships as fifteen pieces, not one link: the written and edited release, a permanent canonical URL, structured data, an atomic claims file, a markdown mirror, narrated audio plus a podcast episode and transcript, four feed formats, an IndexNow push, social posts, syndication to our news site, a relevance-matched network placement, a verified business directory profile, an embeddable newsroom for your own site, and a public citation receipt. The full manifest with what each one does is on the <a href=\"/pricing/\">pricing page</a>."] },
    { id: "distribution",
      k: ["distribute","distribution","distributed","where does it go","where does it land","channel","channels","outlets","outlet","syndication","syndicate","syndicated","reach","who sees it","how many sites","media list","wire"],
      a: ["We run the channels that are genuinely open to anyone, automatically: IndexNow push to Bing, Yandex, Naver and Seznam; RSS, Atom, JSON Feed and Media RSS; a podcast feed; Bluesky and Mastodon; our own news site and network; and a public receipt showing exactly where yours landed. We don't sell access to closed contract wires like AP, and we don't publish an outlet count we can't show you. <a href=\"/press-release-distribution-channels/\">Here's every channel, named.</a>"] },
    { id: "guarantee",
      k: ["guarantee","guaranteed","guarantees","promise","promises","will i rank","rank number one","number one","first page","top of google","get me on","ensure","assure","results"],
      a: ["No \u2014 and anyone promising it is guessing. Rankings, pickup and AI citations are decided by systems nobody here controls. What we can promise is that every open channel runs on your release, every artifact ships, and the receipt page shows you exactly what happened. That's checkable. A ranking promise isn't."] },
    { id: "ai",
      k: ["chatgpt","chat gpt","ai search","ai visibility","perplexity","gemini","copilot","claude","llm","llms","cited","citation","citations","ai overview","ai overviews","ai mode","aio","geo","generative","get cited","answer engine"],
      a: ["Honest version: press releases are a weak lever for AI citations on buying questions and a real one for news-shaped questions. Published research puts wire content in a small share of AI citations overall, while tracking of distributed stories found brand presence around the high teens on Google's AI surfaces and single digits on ChatGPT. Structure moves it more than spend \u2014 facts up top, specific numbers, attributed quotes. <a href=\"/ai-press-release/\">The full picture with sources is here.</a>"] },
    { id: "seo",
      k: ["seo","backlink","link juice","dofollow","anchor","ranking benefit","do links","link building"],
      a: ["We don't sell followed links. Google names press releases in its link spam policy where payment plus ranking-credit links are involved, so every link in a paid release carries rel=\"sponsored\" and every release is labeled as paid. The SEO value that's left is real but different: a permanent indexed URL, entity signals, and brand mentions. <a href=\"/press-release-seo/\">Written up in full here.</a>"] },
    { id: "newsworthy",
      k: ["newsworthy","should i","worth it","do i need","is it worth","right for me","good idea","waste"],
      a: ["Depends entirely on whether you have news. Funding, launches, hires, partnerships, milestones, data \u2014 those work. \"We're still in business and we're great\" doesn't, and I'd rather tell you that than take $99. The <a href=\"/tools/newsworthiness-check/\">newsworthiness check</a> gives you a straight verdict in about a minute, free, no email."] },
    { id: "tools",
      k: ["tool","tools","free","free tool","calculator","generator","checker","analyze","what tools"],
      a: ["Six free tools, no signup, nothing emailed: a release grader, a newsworthiness check, a schema generator, a template builder, a headline scorer, and a cost calculator. They all run in your browser \u2014 nothing you paste is sent anywhere. <a href=\"/tools/\">Start here.</a>"] },
    { id: "grader",
      k: ["grade","grader","score","audit my release","review my release","check my release"],
      a: ["Paste your draft into the <a href=\"/tools/press-release-grader/\">release grader</a> and it scores twelve things AI engines and editors actually read for \u2014 fact density up top, specific numbers, attributed quotes, headline shape, dateline, boilerplate bloat, link handling. Free, instant, and it runs entirely in your browser."] },
    { id: "write",
      k: ["write","writing","draft","who writes","do you write","copy","wordsmith"],
      a: ["Writing and one editorial pass are included in the $99 \u2014 you send the facts, we write it. If you'd rather write it yourself, the <a href=\"/tools/press-release-template/\">template builder</a> and <a href=\"/how-to-write-a-press-release/\">writing guide</a> are free. Which way do you want to go?"] },
    { id: "audio",
      k: ["audio","podcast","voice","listen","narrat","spotify","apple podcast","mp3","sound"],
      a: ["Every release gets narrated and published as an episode on our news podcast feed, which carries to Spotify, Apple Podcasts, Amazon Music and YouTube. You get the MP3, a transcript, an embeddable player, and a short clip any podcaster can use for free with attribution. AI narration is disclosed on every episode. <a href=\"/podcast/\">More on that here.</a>"] },
    { id: "newsroom",
      k: ["newsroom","press page","press room","my website","on my site","embed","widget"],
      a: ["Free with every plan. You get a hosted newsroom at our domain plus an embeddable widget for your own site, so your press page updates itself every time you publish. It's schema-marked, so it doubles as a credibility signal on your own domain. <a href=\"/newsroom/\">Details here.</a>"] },
    { id: "directory",
      k: ["directory","listing","business profile","usabusinesssearch","local listing"],
      a: ["Every release includes a verified standard listing on our national business directory, and your releases stack up on that profile over time. That builds a real entity page \u2014 which matters because AI systems need to tell your business apart from every other one with a similar name. An upgraded profile with photos, hours and services is optional."] },
    { id: "howlong",
      k: ["how long","how fast","turnaround","turn around","when will","when do","timeline","how quick","how soon","same day","lead time","deadline"],
      a: ["Drafting and the editorial pass usually take one to two business days once we have your facts. Publishing, feeds, IndexNow push and social go out within minutes of approval. What search engines and AI systems do after that runs on their schedule, not ours."] },
    { id: "revisions",
      k: ["revision","edit","change","rewrite","fix it","another draft","not happy"],
      a: ["One editorial pass is included. Anything we got wrong, we fix free \u2014 always. Changes you request after approving the draft are $25 each. Keeps the price at $99 instead of building an endless-revisions cushion into everyone's bill."] },
    { id: "payment",
      k: ["pay","payment","credit card","invoice","checkout","stripe","paypal","how do i buy","order"],
      a: ["Right now we invoice directly \u2014 send your details through the <a href=\"/contact/\">order form</a> and you'll get an invoice back with payment instructions. Card checkout is being wired up. Nothing is charged until you've approved the scope."] },
    { id: "refund",
      k: ["refund","money back","cancel","guarantee refund","return"],
      a: ["Before we publish, you can cancel for a full refund. Once a release is live it's on permanent public URLs and pushed into feeds, so it can't be unpublished retroactively \u2014 that's why the approval step exists. Corrections are always free. <a href=\"/terms/\">Full terms here.</a>"] },
    { id: "compare",
      k: ["compare","versus","vs","competitor","prnewswire","pr newswire","businesswire","business wire","ein","ereleases","prweb","24-7","better than","difference"],
      a: ["The big wires carry contract distribution to places like AP and financial terminals \u2014 relationships built over decades, and we'd be lying to claim them. What we do is run every open channel automatically and hand you fifteen artifacts plus a public receipt at $99. If AP terminal placement is what your announcement needs, a legacy wire is the right call. The <a href=\"/pricing/\">published price comparison is here</a> so you can judge it yourself."] },
    { id: "agency",
      k: ["agency","agencies","white label","whitelabel","reseller","resell","bulk","client","clients","my client","multiple","volume","wholesale","for my clients","on behalf"],
      a: ["There's an agency block \u2014 25 releases for $1,495, white-labeled, so you can fold it into your own retainers. Worth a conversation rather than a form. <a href=\"/contact/\">Start here</a> and mention volume."] },
    { id: "human",
      k: ["human","person","real person","talk to someone","call me","representative","speak to","agent","sales"],
      a: ["Of course. The <a href=\"/contact/\">contact page</a> has the form and the phone number, and everything there reaches an actual person. Want me to point you at anything specific first?"] },
    { id: "who",
      k: ["who are you","what are you","are you real","are you human","are you a bot","are you ai","your name"],
      a: ["I'm Wire, a programmed assistant for Distribute Press Releases \u2014 not a person, and not an AI model either. I work from a fixed script, so I'll tell you when I don't know something rather than invent it. For anything beyond that, <a href=\"/contact/\">a human is here</a>."] },
    { id: "trust",
      k: ["scam","legit","trust","real company","who runs","about you","behind this","spam"],
      a: ["Fair thing to ask in this category. We're run by Eye To Ad Media, a Denver agency that's been doing search work since 2012, and we built this because we needed it for our own companies first. Everything we publish is labeled as paid, links are marked sponsored, and every release gets a public receipt page anyone can check. <a href=\"/about/\">More on that here.</a>"] },
    { id: "agents",
      k: ["api","agent","mcp","machine readable","json","feed url","developer","integrat","structured"],
      a: ["Everything is machine-readable on purpose \u2014 feeds in four formats, per-release claims files, a markdown mirror, llms.txt, and documented URL patterns for crawlers and agents. It's all at <a href=\"/agents/\">/agents/</a>, free to read, no key needed."] },
    { id: "thanks",
      k: ["thanks","thank you","thx","ty","appreciate","cheers","got it"],
      a: ["Anytime. I'm here if something else comes up."] },
    { id: "bye",
      k: ["bye","goodbye","later","see ya","cya","take care","im out","i'm out","done"],
      a: ["Take care. The free tools are here whenever you want them."] },
    { id: "browsing",
      k: ["just looking","browsing","not now","maybe later","thinking about it","no thanks"],
      a: ["No problem at all. The tools are free and don't ask for an email if you want to poke around."] }
  ];

  var FALLBACK = [
    "I don't have a scripted answer for that one, and I'd rather not guess. A person can help \u2014 <a href=\"/contact/\">contact is here</a>. Want me to cover pricing, distribution channels, or the free tools instead?",
    "That's outside what I've been given. Rather than make something up: <a href=\"/contact/\">a human can answer it</a>. In the meantime I can walk you through what's included or what a release realistically does."
  ];

  var GREETING = "Hey \u2014 I'm Wire, the desk assistant here. I can explain what a release actually does, what it costs, and when it's the wrong tool. What's on your mind?";
  var QUICK = [
    ["What's included?", "what do i get"],
    ["Pricing", "price"],
    ["Where does it go?", "distribution"],
    ["Will ChatGPT cite it?", "chatgpt"],
    ["Free tools", "tools"]
  ];

  /* ----- matching ----- */
  function norm(s) {
    return (" " + s.toLowerCase() + " ")
      .replace(/[^\w\s$']/g, " ")
      .replace(/\bu\b/g, "you").replace(/\br\b/g, "are")
      .replace(/\bpls\b|\bplz\b/g, "please")
      .replace(/\bcost(s|ing)?\b/g, "cost")
      .replace(/\bprices\b/g, "price")
      .replace(/\b(mcuh|muhc|mcuch)\b/g, "much")
      .replace(/\b(pirce|prcie|proce)\b/g, "price")
      .replace(/\b(recieve|reciept)\b/g, "receipt")
      .replace(/\b(guarentee|garuntee|guarante)\b/g, "guarantee")
      .replace(/\b(newsrooms)\b/g, "newsroom")
      .replace(/\b(clients|client's)\b/g, "client")
      .replace(/\b(releases|release's)\b/g, "release")
      .replace(/\b(tools)\b/g, "tool")
      .replace(/\b(podcasts)\b/g, "podcast")
      .replace(/\b(channels)\b/g, "channel")
      .replace(/\b(refunds)\b/g, "refund")
      .replace(/\b(revisions)\b/g, "revision")
      .replace(/\b(headlines)\b/g, "headline")
      .replace(/\b(links)\b/g, "link")
      .replace(/\b(feeds)\b/g, "feed")
      .replace(/\bseoo?\b/g, "seo")
      .replace(/\bpr\b/g, "press release")
      .replace(/\s+/g, " ");
  }
  function match(input) {
    var t = norm(input), best = null, bestScore = 0;
    for (var i = 0; i < K.length; i++) {
      var score = 0;
      for (var j = 0; j < K[i].k.length; j++) {
        var kw = K[i].k[j];
        // whole-word match only: "airspeed" must not match "speed",
        // and "ai" must not match the start of "aiming".
        if (t.indexOf(" " + kw + " ") > -1) {
          score += kw.length > 6 ? 3 : (kw.indexOf(" ") > -1 ? 3 : 2);
        }
      }
      // short greetings shouldn't beat a real question
      if (K[i].id === "greet" && t.trim().split(" ").length > 4) score = 0;
      if (score > bestScore) { bestScore = score; best = K[i]; }
    }
    if (!best || bestScore < 2) return FALLBACK[Math.floor(Math.random() * FALLBACK.length)];
    return best.a[Math.floor(Math.random() * best.a.length)];
  }

  /* ----- markup ----- */
  var tab = document.createElement("button");
  tab.id = "dpr-bot-tab";
  tab.type = "button";
  tab.setAttribute("aria-label", "Open the Wire assistant");
  tab.textContent = "Ask Wire";

  var panel = document.createElement("div");
  panel.id = "dpr-bot";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Wire assistant");
  panel.innerHTML =
    '<div class="bot-head">' +
      '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
        '<rect width="24" height="24" rx="7" fill="#0284FE"/>' +
        '<path d="M8 7h5l3 3v7a1.5 1.5 0 0 1-1.5 1.5h-6A1.5 1.5 0 0 1 7 17V8.5A1.5 1.5 0 0 1 8.5 7Z" fill="#fff"/>' +
        '<path d="M13 7l3 3h-3z" fill="#A9D6FF"/>' +
      '</svg>' +
      '<div><strong>Wire</strong><small>Desk assistant \u00b7 not a person</small></div>' +
      '<button class="bot-x" type="button" aria-label="Close">\u00d7</button>' +
    '</div>' +
    '<div class="bot-log" id="bot-log" aria-live="polite"></div>' +
    '<div class="bot-quick" id="bot-quick"></div>' +
    '<form class="bot-in" id="bot-form">' +
      '<label class="sr-only" for="bot-input">Message</label>' +
      '<input id="bot-input" type="text" autocomplete="off" placeholder="Ask about price, channels, tools\u2026">' +
      '<button type="submit" aria-label="Send">Send</button>' +
    '</form>';

  document.body.appendChild(tab);
  document.body.appendChild(panel);

  var log = panel.querySelector("#bot-log");
  var quick = panel.querySelector("#bot-quick");
  var form = panel.querySelector("#bot-form");
  var input = panel.querySelector("#bot-input");
  var started = false;

  function add(html, who) {
    var b = document.createElement("div");
    b.className = "bub bub-" + who;
    b.innerHTML = html;
    log.appendChild(b);
    log.scrollTop = log.scrollHeight;
  }
  function respond(text) {
    add(text.replace(/</g, "&lt;").replace(/>/g, "&gt;"), "u");
    setTimeout(function () { add(match(text), "b"); }, 320);
  }

  QUICK.forEach(function (q) {
    var b = document.createElement("button");
    b.type = "button";
    b.textContent = q[0];
    b.addEventListener("click", function () { respond(q[1]); });
    quick.appendChild(b);
  });

  function open() {
    panel.classList.add("open");
    tab.style.display = "none";
    if (!started) { add(GREETING, "b"); started = true; }
    input.focus();
  }
  function close() { panel.classList.remove("open"); tab.style.display = ""; }

  tab.addEventListener("click", open);
  panel.querySelector(".bot-x").addEventListener("click", close);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && panel.classList.contains("open")) close();
  });
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var v = input.value.trim();
    if (!v) return;
    input.value = "";
    respond(v);
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-open-wire]"), function (el) {
    el.addEventListener("click", function (e) { e.preventDefault(); open(); });
  });
})();
