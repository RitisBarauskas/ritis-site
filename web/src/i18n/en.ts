import type { Content, FaqContext } from './content';
import type { Prices } from '../site.config';

const en: Content = {
  meta: {
    title: 'Ritis — an engineer who knows what to ask AI',
    description:
      'I take an idea or a prototype to a product that works and causes no trouble: a repository with rules and checks for AI agents, architecture in code, fixes before launch. Calls in Russian or broken English.',
  },
  badge: 'demo · ritis.dev',
  nav: {
    label: 'Sections',
    ask: 'How I work with AI',
    models: 'Models',
    help: 'How I help',
    about: 'About me',
    theme: 'Switch theme',
    languages: 'Site language',
    cta: 'Ritis, let’s start a project',
  },
  footer: {
    label: 'Footer',
    offer: 'Public offer',
    refund: 'Refunds',
    privacy: 'Privacy',
    details: 'Business details',
  },
  hero: {
    eyebrow: 'Engineer · AI products that don’t break',
    titleHtml: 'AI is like a driving licence. You have the licence, but you can’t&nbsp;<mark>drive</mark>.',
    leadHtml:
      '<b>I know not just the roads but the potholes in them — and how the car works.</b> I’ll help you take an idea or a prototype to a product that works and causes no trouble.',
    cta: 'I want results, not looks',
    ctaAsk: 'How I work with AI ↓',
    micro: 'A Google Meet call · the result lands in your repository · in Russian or broken English',
    photoAlt: 'Ritis Barauskas',
    stickerHtml: 'How I look at&nbsp;“the AI said it’s all&nbsp;fine”',
  },
  facts: [
    { valueHtml: '2,500+', text: 'student projects reviewed as a code reviewer' },
    { valueHtml: '≈&nbsp;1,000', text: 'graduates went from zero to junior developer under my mentoring' },
    { valueHtml: '7+', text: 'years in software development, in lead roles' },
    { valueHtml: '4+', text: 'years as a mentor and reviewer at Yandex Practicum' },
  ],
  why: {
    label: 'Why me',
    titleHtml: 'Anyone can build a prototype with AI. A product that doesn’t&nbsp;break — only a few',
    sub: 'Everything works in a demo. The trouble starts when real users, money and data arrive: repeated payments, simultaneous requests, leaks, “why was the customer charged twice”.',
    cards: [
      {
        k: 'before the start',
        title: 'Requirements and architecture',
        textHtml:
          'What we build, for whom and from what: requirements, architecture, stages, budget — in the repository, next to the code. Where a corner can be cut, and where a cut corner will later cost more than the whole project.',
      },
      {
        k: 'before production',
        title: 'Where it breaks',
        textHtml:
          '2,500+ student projects have shown me almost every way to write code that “works”. I know where it will break before it breaks for you.',
      },
      {
        k: 'inside AI',
        title: 'How AI works',
        textHtml:
          'How models and AI agents work, why AI sounds confident when it is wrong, and why code is fine in every file yet falls apart where the files meet.',
      },
    ],
  },
  ask: {
    label: 'How I work with AI',
    titleHtml: 'The Room of Requirement opens to those who know what&nbsp;to&nbsp;ask',
    sub: 'Remember the Room of Requirement from Harry Potter? It appears only to someone who knows exactly what they need. Everyone else walks past a bare wall. AI is the same: a model will find the vulnerability if you ask the right way. If you don’t know what to look for, you will never find it.',
    codeLabel: 'Code sample',
    generated: 'written by AI',
    codeCaption: 'A typical payment handler that AI readily writes. The code stays the same — only the question changes.',
    tabsLabel: 'How to ask AI',
    tabs: { naive: 'How people usually ask', pro: 'How I ask', real: 'How it really works' },
    you: 'you',
    me: 'me',
    ai: 'AI',
    naive: {
      question: 'Check my payment code for bugs.',
      answer:
        'The code is neat and easy to read 👍 You could add type annotations, move the "/webhooks/payment" path into a constant and write a docstring. I don’t see any critical issues.',
      verdict: 'Zero findings. The code goes to production with a hole that lets anyone “pay” for an order with a single request.',
    },
    pro: {
      prompt: `This is a payment notification handler. The money is real, the launch is tomorrow.
Check only the following, and for each point show the line and how it fails:
1. Is the payment provider’s signature verified before any work with the data?
2. What happens if the same notification arrives twice? Providers retry delivery.
3. What happens if two notifications for one order arrive at the same time?
4. What units are amount and paid in? Where is the transaction ledger?
Don’t discuss style, types or names. If a point is fine, say so — don’t make things up.`,
      intro: 'Found four problems. Click any of them — I’ll highlight the line.',
      findings: [
        { lines: '1-2', sev: 'r', meta: 'critical · lines 1–2', text: 'The signature is not verified. Anyone can “pay” for an order with one POST request.' },
        { lines: '4', sev: 'r', meta: 'critical · line 4', text: 'A repeated delivery means a double credit. It needs idempotency by event id.' },
        { lines: '3-5', sev: 'o', meta: 'important · lines 3–5', text: 'A race: two simultaneous notifications read the old value and overwrite each other.' },
        { lines: '4', sev: 'y', meta: 'worth fixing · line 4', text: 'The units are not reconciled and there is no ledger — later no one can tell what happened to the money.' },
      ],
      verdict: 'Same code. Same model. The only difference is the question.',
      next: 'Truth is, I don’t ask like that either →',
    },
    real: {
      preface: 'If you have read this far',
      confessHtml: '<b>To tell the truth, I don’t ask like that either.</b> Otherwise my productivity would drop below zero.',
      text: 'I set the constraints, working rules and code requirements up front. So the agent comes up with these questions itself and asks them of itself when it cross-checks its work.',
      rulesCaption: 'Project rules · set once, before the first line of code',
      rulesHtml: `<span class="c"># CLAUDE.md — excerpt</span>
<span class="h">## Money</span>
- The balance changes only through the transaction ledger.
- Amounts are integers in cents, the currency is explicit.
<span class="h">## Incoming notifications</span>
- The signature is verified before the body is read.
- A repeated delivery does not change the result:
  idempotency by event id.
<span class="h">## Before handing in a task</span>
- Cross-check: ask yourself about retries,
  races and access rights, answer with the line.
- Found a broken rule — fix it, don’t describe it.`,
      request: 'Write a payment notification handler.',
      aiWho: 'AI · cross-check before handing in',
      intro: 'The draft on the left breaks the project rules in four places. Fixed before handing in:',
      findings: [
        { lines: '1-2', meta: 'fixed · lines 1–2', text: 'The payment provider’s signature is verified before the body is read.' },
        { lines: '4', meta: 'fixed · line 4', text: 'A repeated notification with the same event id is ignored.' },
        { lines: '3-5', meta: 'fixed · lines 3–5', text: 'An atomic update instead of “read — change — save”.' },
        { lines: '4', meta: 'fixed · line 4', text: 'The amount is in cents; the balance changes through the ledger.' },
      ],
      verdict: 'The questions are the same. Only it isn’t me asking them — the agent asks itself, on every task.',
    },
    statement:
      'I don’t read code line by line — today AI does it faster and more carefully. My job is to know what to ask, which constraints to set and which finding to trust.',
    whyTitle: 'Why AI says “everything is great”',
    why: [
      { k: '01', title: 'It answers exactly the question', text: 'Ask “are there any bugs” and you get a list of trifles. About signatures, retries and races it stays silent until you ask about them.' },
      { k: '02', title: 'It doesn’t know your context', text: 'AI doesn’t know that the money is real, that the provider retries notifications and that a thousand users arrive tomorrow. That knowledge has to be given to it.' },
      { k: '03', title: 'It wants to please', text: 'Models tend to agree with you and sound confident even when they are wrong. Without constraints you get a compliment instead of a review.' },
    ],
  },
  models: {
    label: 'Which model to take',
    titleHtml: 'A tractor, a helicopter and a speedboat are all transport. But&nbsp;to&nbsp;the airport you take a&nbsp;taxi',
    subs: [
      'If you need to get yourself and a suitcase from home to the airport, car sharing or a taxi is the better deal. You can take your own car — you will overpay for parking at the terminal, but you travel in comfort and on your own wheels.',
      'AI is the same. Models differ, tasks differ — and so do the price and the result.',
    ],
    vehicles: [
      { icon: '🚕', title: 'Taxi and car sharing', eq: '= an AI chat or a ready-made service', text: 'Get in and go, pay per ride. For one-off tasks: a letter, a text, sketching an idea, making sense of someone else’s code.', when: 'The car is not yours: someone else’s rules, someone else’s prices, and your data rides in someone else’s car.' },
      { icon: '🚗', title: 'Your own car', eq: '= an AI agent in the editor + a repository with rules', text: 'More expensive at the start, and every month there is “parking at the terminal”: subscriptions and tokens. But the agent knows your project and your rules.', when: 'When you are building a product, not taking a one-off ride.' },
      { icon: '🚜', title: 'Tractor', eq: '= a pipeline of agents, your own model, fine-tuning', text: 'Powerful, it will plough through anything. But if you are going to the airport, it is slow, expensive and funny.', when: 'When the task really is heavy and repeats thousands of times.' },
      { icon: '🚁', title: 'Helicopter', eq: '= the most powerful model for every trifle', text: 'It gets there fast and in style. But the bill for a fixed typo will look like a flight.', when: 'For hard decisions — yes. For routine — overpaying.' },
      { icon: '🚤', title: 'Speedboat', eq: '= a tool made for a different environment', text: 'Say, a no-code builder where money, access rights and load are at stake. A great speedboat — just the wrong road.', when: 'When “everyone does it”, but your task is a different one.' },
    ],
    stripValueHtml: 'up&nbsp;to&nbsp;40×',
    stripHtml:
      'That is how much the price of a light and a flagship model from the same vendor can differ. A light one is often enough, and sometimes saving on the model costs more than the model itself. <strong>I wire models into the code for your task:</strong> where a cheap model will do, where you need a flagship and where you need no AI at all — with the cost worked out in the README.',
  },
  offers: {
    label: 'How I help',
    title: 'Four formats of work',
    sub: 'You pay for the result, not for my time: every format ends with code in your repository.',
    cards: {
      start: {
        tag: 'start here',
        title: 'Technical start',
        priceNote: 'a call and 5 working days',
        desc: 'We have a call and get to grips with the task and the goals. Then I put together a repository to build it from — on your own, with AI agents or with a contractor.',
        itemsHtml: [
          'A Google Meet call — I study your materials beforehand',
          'A project skeleton for your task',
          'Rules and constraints for AI agents, checks in CI',
          'A README on how to carry on',
        ],
        cta: 'Start',
      },
      foundation: {
        tag: 'the main one',
        title: 'Foundation: from idea to repository',
        priceNote: '2–3 weeks',
        desc: 'I set up the project so that you can keep building it on your own with AI agents or hand it to any contractor — and check their work.',
        itemsHtml: [
          'Requirements and user scenarios — in the repository, next to the code',
          'Architecture and stack — in code: a working skeleton, not a diagram',
          'Models and tools wired in where they are needed, the monthly cost worked out in the README',
          'Rules, constraints and code requirements for AI agents, CI checks and the first tests',
          'Stages and deadlines — as tasks in the repository',
        ],
        cta: 'Begin with the technical start',
      },
      launch: {
        tag: '',
        title: 'Launch preparation',
        priceNote: 'up to 7 working days',
        desc: 'Your prototype already works? I take it up to real users and real money. AI looks for problems with my questions and constraints, and I fix what it finds right in your repository.',
        itemsHtml: [
          'Secrets and keys out of the code, access rights kept to a minimum',
          'Linter, tests and security checks in CI',
          '<span>Critical <i class="dot-r"></i> <i class="dot-o"></i> <i class="dot-y"></i> issues in payments, data and where modules meet — fixed in pull requests</span>',
          'Rules for AI agents so the bugs don’t come back',
        ],
        cta: 'Choose',
      },
      subscription: {
        tag: '',
        title: 'Development subscription',
        priceNote: 'for those who build on their own',
        desc: 'You build — I write code alongside you: architecture, quality, rules for AI agents. So that in six months you don’t have to rewrite everything.',
        itemsHtml: [
          'Every month — development on agreed tasks: commits and pull requests to your repository',
          'Rules for AI agents and CI checks grow with the project',
          'I fix whatever breaks the architecture',
        ],
        cta: 'Begin with the technical start',
      },
    },
    note: (prices: Prices) =>
      `Packages begin with the technical start for ${prices.start} — its price counts towards the package if you order it. I can propose the scope and the price of a package after the technical start.`,
    paymentLabel: 'Payment methods',
    paymentNote: 'Payment in lari by Visa or Mastercard; if your card is in another currency, your bank sets the exchange rate.',
  },
  honest: {
    label: 'Honestly',
    titleHtml: 'I can build products. Sell them&nbsp;— <mark>no</mark>',
    subs: [
      'I can build products from idea to launch — ones that work and cause no trouble. But I can’t sell them. That is why you haven’t heard of my own projects.',
      'Then again… if you ended up here, maybe it’s not all that bad.',
    ],
    cta: 'I want to start!',
    yesTitle: 'What I help with',
    yes: [
      'a product that holds up to real users, money and data',
      'an architecture you won’t have to rewrite in six months',
      'AI that does what you need, not what you happened to ask for',
      'a project in a repository you can hand to any contractor — and check their work',
    ],
    noTitle: 'Wrong address if you need',
    no: ['to work out what to sell and how', 'your first million or your first customers', 'promotion, marketing, funnels', 'someone to tell you everything is great'],
    note: 'Promotion and sales are not my field. But once you find someone who can sell, the product won’t fall apart in their hands.',
  },
  process: {
    label: 'How it works',
    title: 'From booking to repository in four steps',
    steps: [
      { title: 'Booking and payment', text: 'You choose a format and pay. Within a working day I write to you to schedule the call.' },
      { title: 'A short form', text: 'What needs to be done, links to code, mock-ups, documents. I study them beforehand.' },
      { title: 'A Google Meet call', text: 'We get to grips with the task and the goals, in Russian or broken English. Recorded if you wish.' },
      { title: 'The repository', text: 'Code, rules and checks for AI agents, and a README on how to carry on. Each format states its deadline.' },
    ],
  },
  about: {
    photoAlt: 'Ritis Barauskas',
    label: 'About me',
    title: 'Hi, I’m Ritis',
    parasHtml: [
      'More than seven years in software development — in lead roles at Russian and international companies.',
      'Since 2022, a mentor and reviewer at Yandex Practicum: more than 2,500 reviewed student projects and almost a thousand graduates who went from zero to junior developer under my mentoring. I have seen thousands of times where code breaks for those who are just starting — and I know which constraints prevent it.',
      'I work with AI agents every day. I know what each model can do, what it costs and where you still can’t do without an engineer.',
    ],
    principles: [
      { title: 'Quality from the start', text: 'Not “ship it now, refactor later”. A bad plan I rework before we start.' },
      { title: 'I say it as it is', text: 'If an idea or code is bad, I say so directly — and explain why.' },
      { title: 'Simpler, not more complex', text: 'A good solution usually removes what is superfluous rather than adding one more layer.' },
      { title: 'No magic', text: 'Everything I do stays in your repository with a README: you can carry on without me.' },
    ],
    quote: '“AI will answer any question. All the work is knowing which question to ask.”',
    quoteNote: 'the rule I work by with any code and any model',
  },
  channel: {
    label: 'Ritis Do It',
    title: 'I show how I do it myself',
    sub: 'On YouTube and Telegram, in Russian, I show honestly how to build products with AI: which questions I ask models and what they find, projects from start to finish, teardowns of viewers’ repositories, mistakes and how they get fixed. The first series is a trading bot: how to write it properly, set constraints and not lose money on a bug.',
    series: ['questions for AI', 'repository teardowns', 'projects from start to finish', 'a trading bot'],
    teardown: 'Send a repository for a teardown on video',
    caption: 'When I found passwords right in the repository',
  },
  veritas: {
    soon: 'soon',
    title: ' — my questions on autopilot',
    sub: 'Paste a link to a public repository. AI will go through it with my questions and constraints and produce a report: what will break, where the holes are and what to fix first.',
    repoPlaceholder: 'https://github.com/you/your-repository',
    repoLabel: 'Repository link',
    emailPlaceholder: 'Email — I’ll write when we launch',
    emailLabel: 'Email',
    submit: 'Join the waitlist',
  },
  faq: {
    label: 'Questions',
    title: 'What people usually ask',
    items: [
      { q: 'How is this better than asking ChatGPT or Claude myself?', a: () => 'It isn’t — if you know what to ask. AI answers exactly the question it is asked and readily agrees. I turn the questions you didn’t know existed into rules and checks in your repository: AI agents work within them, and CI catches where AI sounds confident but is wrong.' },
      { q: 'Will you read my code yourself?', a: () => 'Not line by line, and there is no need: today AI does it faster and more carefully. My job is to give it the right questions and constraints, check every finding, weed out the false ones and fix what matters in your repository.' },
      { q: 'Which models do you wire in?', a: () => 'Whatever fits the task and the budget. The price of a light and a flagship model from the same vendor differs up to 40 times, and paying for a flagship model on routine work soon adds up. In the technical start and the Foundation I wire models into the code and leave the cost worked out in the README.' },
      { q: 'Will you help with promotion and the first customers?', a: () => 'No. It is not my field, and I say so honestly. I will help make sure that by the time customers come, the product works and causes no trouble.' },
      { q: 'Do I need to understand programming?', a: () => 'No. With founders I speak the language of business: money, deadlines, risks. With developers, the language of code.' },
      { q: 'What should I prepare for the call?', a: () => 'Describe the task briefly and send everything you have: a link to the repository, mock-ups, documents. The more you send in advance, the more precise the result.' },
      { q: 'In what language?', a: () => 'In Russian or in broken English.' },
      { q: 'How do I pay?', a: ({ prices }: FaqContext) => `When you book, in lari by Visa or Mastercard: the technical start is ${prices.start}, launch preparation is ${prices.launch}. Packages begin with the technical start; its price counts towards the package if you order it.` },
      { q: 'What if I change my mind?', a: ({ refund }: FaqContext) => `Until the result is delivered, you can withdraw at any time. How much comes back depends on what has already been done for the order — it is all set out in the <a href="${refund}">refund terms</a>.` },
    ],
  },
  final: {
    title: 'Show me your idea or prototype. Within 5 working days of the call you will have a repository to build it from.',
    cta: 'Start my project',
  },
  dialog: {
    title: 'Tell me about the project',
    close: 'Close',
    steps: ['form', 'payment', 'call', 'repository'],
    formatLabel: 'Format',
    formats: {
      start: 'Technical start',
      foundation: 'Foundation: from idea to repository',
      launch: 'Launch preparation',
      subscription: 'Development subscription',
      teardown: 'A free teardown on video',
    },
    name: 'Your name',
    contact: 'Email or Telegram',
    about: 'What needs to be done?',
    aboutPlaceholder: 'A couple of sentences about the task',
    links: 'Links (repository, mock-ups, documents)',
    linksPlaceholder: 'optional',
    honeypot: 'Additional',
    consentHtml: (offer: string, privacy: string) =>
      `I accept the <a href="${offer}" target="_blank">public offer</a> and have read the <a href="${privacy}" target="_blank">privacy policy</a>`,
    startNowHtml: (refund: string) =>
      `I ask for the work to start right after payment. If I withdraw, I pay for the stages already delivered to the repository and for the services bought for the order; once the result is delivered, I can no longer withdraw, except for its defects. <a href="${refund}" target="_blank">Refund terms</a>`,
    note: 'Payment in lari by Visa or Mastercard; if your card is in another currency, your bank sets the exchange rate. After payment I contact you to schedule the call and send you a Google Meet link.',
    testNote: 'Test mode: no money is charged, and only a test card will work.',
  },
  bookingPage: {
    title: 'Booking — ritis.dev',
    description: 'The payment status of a booking.',
    checkingText: 'This takes a few seconds.',
    retry: 'Pay again →',
    resume: 'Back to the payment →',
    home: 'Home page',
    testNote: 'Test mode: no money is charged.',
  },
  legal: {
    revised: (date: string) => `Revised ${date}`,
    merchantName: 'Individual Entrepreneur Ritis Barauskas',
    registry: 'National Agency of Public Registry of Georgia',
    country: 'Georgia',
    requisites: {
      seller: 'Contractor',
      registryId: 'Registration number',
      country: 'Country of registration',
      email: 'Email',
    },
  },
};

export default en;
