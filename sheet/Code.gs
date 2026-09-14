/**
 * Mesa Academic League study site -- the content sheet's publish button.
 *
 * Paste this whole file into the sheet's Extensions > Apps Script editor, save,
 * and reload the sheet. A "Study site" menu appears:
 *
 *   Publish to site          commits the sheet to content/content.json in the
 *                            GitHub repo; a GitHub Action checks it, rebuilds
 *                            index.html, and this reports back what happened.
 *   Regenerate study guide   rewrites the printable study guide, a Google Doc,
 *                            from this sheet. Nothing leaves Google: the
 *                            packet is never put in the public repo.
 *   Pull content from site   replaces every tab with what the repo holds.
 *   Connect to GitHub...     stores the token the other two use.
 *
 * The sheet is dumb transport on purpose. Which column feeds which field, and
 * what counts as valid, all live in tools/content.py in the repo, where they
 * are tested; this file only moves strings. Its one piece of real logic is the
 * file format, which must match dump_content() in tools/content.py byte for
 * byte, or "nothing changed" stops being detectable.
 */

var GH = { owner: 'mariopolito', repo: 'mesa-academic-league', branch: 'main' };
var CONTENT_PATH = 'content/content.json';
var SCHEMA_PATH = 'content/schema.json';
var WORKFLOW = 'publish.yml';
var README_TAB = 'Read me';
var WAIT_MS = 4.5 * 60 * 1000;   // Apps Script stops a menu function at six minutes

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Study site')
    .addItem('Publish to site', 'publishToSite')
    .addItem('Regenerate study guide', 'regenerateStudyGuide')
    .addSeparator()
    .addItem('Pull content from site (replaces this sheet)', 'pullFromSite')
    .addItem('Connect to GitHub…', 'connectGitHub')
    .addToUi();
}

// ------------------------------------------------------------------ plumbing

function fail_(msg) {
  var e = new Error(msg);
  e.forUser = true;
  throw e;
}

function guarded_(title, fn) {
  try {
    fn();
  } catch (e) {
    var ui = SpreadsheetApp.getUi();
    ui.alert(title, e.forUser ? e.message : 'Something went wrong: ' + e.message +
      '\n\nNothing on the site changed. Send this message to Mario.', ui.ButtonSet.OK);
  }
}

function props_() {
  return PropertiesService.getScriptProperties();
}

function gh_(method, path, body, accept) {
  var token = props_().getProperty('GITHUB_TOKEN');
  if (!token) fail_('This sheet is not connected to GitHub yet. Choose Study site > Connect to GitHub first.');
  var opt = {
    method: method,
    muteHttpExceptions: true,
    headers: {
      Authorization: 'Bearer ' + token,
      Accept: accept || 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28'
    }
  };
  if (body !== undefined) {
    opt.contentType = 'application/json';
    opt.payload = JSON.stringify(body);
  }
  var url = path.indexOf('https://') === 0 ? path : 'https://api.github.com' + path;
  var res = UrlFetchApp.fetch(url, opt);
  var text = res.getContentText();
  var json = null;
  try { json = text ? JSON.parse(text) : null; } catch (err) { json = null; }
  return { code: res.getResponseCode(), json: json, text: text };
}

function repoPath_(rest) {
  return '/repos/' + GH.owner + '/' + GH.repo + rest;
}

function decode_(b64) {
  return Utilities.newBlob(Utilities.base64Decode(b64.replace(/\s/g, ''))).getDataAsString('UTF-8');
}

function encode_(text) {
  return Utilities.base64Encode(Utilities.newBlob(text).getBytes());
}

/** A file in the repo: its text and the blob sha GitHub needs to update it. */
function readRepoFile_(path) {
  var r = gh_('GET', repoPath_('/contents/' + path + '?ref=' + GH.branch));
  if (r.code === 401 || r.code === 403) {
    fail_('GitHub turned the token down (' + r.code + '). It may have expired. ' +
      'Ask Mario for a new one, then choose Study site > Connect to GitHub.');
  }
  if (r.code !== 200 || !r.json) fail_('Could not read ' + path + ' from GitHub (' + r.code + ').');
  var text;
  if (r.json.content && r.json.encoding === 'base64') {
    text = decode_(r.json.content);
  } else {
    // Files over 1 MB come back without content; ask for the raw bytes instead.
    var raw = gh_('GET', repoPath_('/contents/' + path + '?ref=' + GH.branch), undefined,
      'application/vnd.github.raw+json');
    if (raw.code !== 200) fail_('Could not read ' + path + ' from GitHub (' + raw.code + ').');
    text = raw.text;
  }
  return { sha: r.json.sha, text: text };
}

/** The same format tools/content.py dump_content() writes. Keep them in step. */
function dumpContent_(tabs, names) {
  return '{"tabs":{\n' + names.map(function (n) {
    return JSON.stringify(n) + ':[\n' + tabs[n].map(function (row) {
      return JSON.stringify(row);
    }).join(',\n') + '\n]';
  }).join(',\n') + '\n}}\n';
}

// ------------------------------------------------------------------- connect

function connectGitHub() {
  guarded_('Connect to GitHub', function () {
    var ui = SpreadsheetApp.getUi();
    var r = ui.prompt('Connect to GitHub',
      'Paste the GitHub token for ' + GH.owner + '/' + GH.repo + '.\n' +
      '(Fine-grained, this repository only: Contents read and write, Actions read.)',
      ui.ButtonSet.OK_CANCEL);
    if (r.getSelectedButton() !== ui.Button.OK) return;
    var token = r.getResponseText().trim();
    if (!token) return;
    var previous = props_().getProperty('GITHUB_TOKEN');
    props_().setProperty('GITHUB_TOKEN', token);
    var check = gh_('GET', repoPath_(''));
    if (check.code !== 200) {
      if (previous) props_().setProperty('GITHUB_TOKEN', previous);
      else props_().deleteProperty('GITHUB_TOKEN');
      fail_('GitHub did not accept that token (' + check.code + '). Nothing was saved.');
    }
    var next = props_().getProperty('CONTENT_SHA')
      ? 'Connected. Publish to site is ready.'
      : 'Connected. Next, choose Study site > Pull content from site to fill in the tabs.';
    ui.alert('Connect to GitHub', next, ui.ButtonSet.OK);
  });
}

// ---------------------------------------------------------------------- pull

function pullFromSite() {
  guarded_('Pull content from site', function () {
    var ui = SpreadsheetApp.getUi();
    var ok = ui.alert('Pull content from site',
      'This replaces everything in this sheet with the content on the site. ' +
      'Edits here that have not been published will be lost.\n\nContinue?',
      ui.ButtonSet.YES_NO);
    if (ok !== ui.Button.YES) return;
    var ss = SpreadsheetApp.getActive();
    ss.toast('Reading the site’s content…', 'Study site', 30);
    var schema = JSON.parse(readRepoFile_(SCHEMA_PATH).text);
    var content = readRepoFile_(CONTENT_PATH);
    var tabs = JSON.parse(content.text).tabs;

    writeReadme_(ss, schema.readme);
    schema.tabs.forEach(function (spec) {
      writeTab_(ss, spec, tabs[spec.name] || [spec.columns.map(function (c) { return c.h; })]);
    });
    var blank = ss.getSheetByName('Sheet1');
    if (blank && blank.getLastRow() === 0 && ss.getSheets().length > 1) ss.deleteSheet(blank);
    ss.setActiveSheet(ss.getSheetByName(README_TAB));
    props_().setProperty('CONTENT_SHA', content.sha);

    var q = (tabs.Questions || []).length - 1;
    ui.alert('Pull content from site', 'Done: ' + q + ' questions and ' +
      schema.tabs.length + ' tabs, as they are on the site now.', ui.ButtonSet.OK);
  });
}

function sheetFor_(ss, name) {
  return ss.getSheetByName(name) || ss.insertSheet(name);
}

function writeReadme_(ss, lines) {
  var sh = sheetFor_(ss, README_TAB);
  sh.clear();
  sh.getRange(1, 1, lines.length, 1).setValues(lines.map(function (l) { return [l]; }));
  sh.getRange(1, 1).setFontWeight('bold').setFontSize(14);
  sh.setColumnWidth(1, 640);
  ss.setActiveSheet(sh);
  ss.moveActiveSheet(1);
}

/** A leading = would be read as a formula and a leading ' is swallowed. */
function cell_(v) {
  v = v == null ? '' : String(v);
  return /^[='+]/.test(v) ? "'" + v : v;
}

function writeTab_(ss, spec, grid) {
  var sh = sheetFor_(ss, spec.name);
  var cols = spec.columns.length;
  var rows = grid.length;
  sh.getProtections(SpreadsheetApp.ProtectionType.RANGE).forEach(function (p) {
    if (p.canEdit()) p.remove();
  });
  sh.clear();
  var room = rows + 200;
  if (sh.getMaxRows() < room) sh.insertRowsAfter(sh.getMaxRows(), room - sh.getMaxRows());
  if (sh.getMaxColumns() < cols) sh.insertColumnsAfter(sh.getMaxColumns(), cols - sh.getMaxColumns());
  var max = sh.getMaxRows();
  sh.getRange(1, 1, max, sh.getMaxColumns()).clearDataValidations();

  // Plain text everywhere, before any value lands, so "2/5" stays a fraction
  // and "1" stays the string the site expects -- including rows typed later.
  sh.getRange(1, 1, max, cols).setNumberFormat('@').setVerticalAlignment('top');

  var values = grid.map(function (r) {
    var out = [];
    for (var j = 0; j < cols; j++) out.push(cell_(r[j]));
    return out;
  });
  sh.getRange(1, 1, rows, cols).setValues(values);

  var head = sh.getRange(1, 1, 1, cols);
  head.setFontWeight('bold').setBackground('#e8ecf3');
  sh.setFrozenRows(1);
  spec.columns.forEach(function (c, j) {
    var col = j + 1;
    sh.setColumnWidth(col, c.w || 120);
    if (c.note) sh.getRange(1, col).setNote(c.note);
    var body = sh.getRange(2, col, max - 1, 1);
    body.setWrap(!!c.wrap);
    if (c.choices) {
      body.setDataValidation(SpreadsheetApp.newDataValidation()
        .requireValueInList(c.choices, true).setAllowInvalid(false).build());
    }
    if (c.lock) {
      body.protect().setDescription(spec.name + ' ' + c.h + ': students’ saved progress is keyed to these')
        .setWarningOnly(true);
    }
  });
}

// ------------------------------------------------------------------- publish

function publishToSite() {
  guarded_('Publish to site', function () {
    var ui = SpreadsheetApp.getUi();
    var ss = SpreadsheetApp.getActive();
    if (!props_().getProperty('GITHUB_TOKEN')) {
      fail_('This sheet is not connected to GitHub yet. Choose Study site > Connect to GitHub first.');
    }
    var base = props_().getProperty('CONTENT_SHA');
    if (!base) {
      fail_('This sheet has not been filled from the site yet, so publishing it could ' +
        'wipe the site’s content. Choose Study site > Pull content from site first.');
    }
    ss.toast('Reading the sheet…', 'Study site', 30);
    var schema = JSON.parse(readRepoFile_(SCHEMA_PATH).text);
    var tabs = {};
    schema.tabs.forEach(function (spec) {
      var sh = ss.getSheetByName(spec.name);
      if (!sh) fail_('The "' + spec.name + '" tab is missing. Tabs can’t be renamed or deleted.');
      tabs[spec.name] = readTab_(sh, spec);
    });
    var names = schema.tabs.map(function (t) { return t.name; });
    var text = dumpContent_(tabs, names);

    var remote = readRepoFile_(CONTENT_PATH);
    if (remote.text === text) {
      props_().setProperty('CONTENT_SHA', remote.sha);
      ui.alert('Publish to site', 'Nothing to publish — the site already has exactly this content.', ui.ButtonSet.OK);
      return;
    }
    if (remote.sha !== base) {
      fail_('The site’s content was changed somewhere other than this sheet since the ' +
        'sheet was last published or pulled. Publishing now would erase that change, so ' +
        'nothing was published.\n\nAsk Mario before going further.');
    }

    ss.toast('Saving to GitHub…', 'Study site', 30);
    var put = gh_('PUT', repoPath_('/contents/' + CONTENT_PATH), {
      message: 'Publish from the content sheet',
      content: encode_(text),
      sha: remote.sha,
      branch: GH.branch
    });
    if (put.code === 409 || put.code === 422) {
      fail_('Someone published at the same moment, so nothing was saved. Wait a minute and publish again.');
    }
    if (put.code !== 200 && put.code !== 201) {
      fail_('GitHub would not save the content (' + put.code + '). Nothing on the site changed.' +
        (put.code === 403 || put.code === 401 ? ' The token may have expired or lack write access.' : ''));
    }
    props_().setProperty('CONTENT_SHA', put.json.content.sha);

    ss.toast('Saved. Checking the content and rebuilding the page…', 'Study site', 120);
    var result = waitForBuild_(put.json.commit.sha);
    ui.alert('Publish to site', result, ui.ButtonSet.OK);
  });
}

/** A tab as a grid of display strings: exactly what is on screen, nothing
 *  typed as a date or a number. Trailing blank rows go; a blank row in the
 *  middle stays, so the row numbers in any error match the sheet. */
function readTab_(sh, spec) {
  var grid = sh.getDataRange().getDisplayValues();
  var width = grid.length ? grid[0].length : 0;
  while (width > 0 && !String(grid[0][width - 1]).trim()) width--;
  grid = grid.map(function (r) { return r.slice(0, width); });
  while (grid.length > 1 && grid[grid.length - 1].every(function (v) { return v === ''; })) grid.pop();
  if (!grid.length) grid = [[]];

  // A new row's ID is filled in here, in the sheet itself, so the number it
  // gets is the one it keeps on every later publish.
  spec.columns.forEach(function (c) {
    if (!c.autoid) return;
    var j = grid[0].indexOf(c.h);
    if (j < 0) return;
    var pat = new RegExp('^' + c.autoid.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(\\d+)$');
    var top = -1;
    grid.forEach(function (r, i) {
      var m = i > 0 && pat.exec(r[j]);
      if (m) top = Math.max(top, parseInt(m[1], 10));
    });
    grid.forEach(function (r, i) {
      if (i === 0 || r[j] !== '') return;
      if (!r.some(function (v) { return v !== ''; })) return;
      top++;
      r[j] = c.autoid + top;
      sh.getRange(i + 1, j + 1).setValue(r[j]);
    });
  });
  return grid;
}

// ---------------------------------------------------------- what happened

function waitForBuild_(commitSha) {
  var deadline = Date.now() + WAIT_MS;
  var run = null;
  while (Date.now() < deadline) {
    Utilities.sleep(5000);
    var r = gh_('GET', repoPath_('/actions/runs?head_sha=' + commitSha + '&per_page=10'));
    var runs = (r.json && r.json.workflow_runs) || [];
    run = runs.filter(function (x) { return String(x.path || '').indexOf(WORKFLOW) >= 0; })[0] || null;
    if (run && run.status === 'completed') break;
  }
  var link = run ? run.html_url
    : 'https://github.com/' + GH.owner + '/' + GH.repo + '/actions';
  if (!run || run.status !== 'completed') {
    return 'Saved. The page is still being rebuilt, which can take a few minutes when ' +
      'GitHub is busy. Nothing more to do here; to watch it finish:\n' + link;
  }
  var notes = annotations_(run);
  if (run.conclusion === 'success') {
    return 'Published. The page in the GitHub repo now matches this sheet.' +
      (notes.warning.length ? '\n\nNotes (published anyway):\n• ' + notes.warning.join('\n• ') : '');
  }
  if (notes.failure.length) {
    return 'Not published — fix these in the sheet and publish again:\n\n• ' +
      notes.failure.join('\n• ') +
      (notes.warning.length ? '\n\nAlso worth a look:\n• ' + notes.warning.join('\n• ') : '');
  }
  return 'Not published. The build failed for a reason that is not in the sheet ' +
    '(' + run.conclusion + '). Send Mario this link:\n' + link;
}

/** The messages tools/content.py wrote, pulled back off the run. GitHub adds
 *  a few of its own, which say nothing about the sheet and are dropped. */
function annotations_(run) {
  var out = { failure: [], warning: [] };
  var jobs = gh_('GET', run.jobs_url);
  ((jobs.json && jobs.json.jobs) || []).forEach(function (job) {
    if (!job.check_run_url) return;
    var a = gh_('GET', job.check_run_url + '/annotations?per_page=50');
    (Array.isArray(a.json) ? a.json : []).forEach(function (x) {
      var msg = String(x.message || '');
      if (/^Process completed with exit code/.test(msg)) return;
      if (/deprecat|Node\.js \d+ actions|set-output|save-state/i.test(msg)) return;
      if (x.annotation_level === 'failure') out.failure.push(msg);
      else if (x.annotation_level === 'warning') out.warning.push(msg);
    });
  });
  out.failure = out.failure.slice(0, 12);
  out.warning = out.warning.slice(0, 8);
  return out;
}

// ------------------------------------------------------------ study guide
//
// The printable packet, rebuilt from the sheet as a Google Doc. It reads the
// same tabs the site does, plus one tab of its own -- "Study guide text", the
// grammar notes, footnotes and title that the site has no use for. That tab is
// not published and Pull never touches it.
//
// The document is rewritten in place, so its link, its sharing and its place
// in Drive survive every regeneration. Only DocumentApp is used, never
// DriveApp, so the sheet never asks for access to the rest of anyone's Drive.

var GUIDE_TAB = 'Study guide text';
var GUIDE_PARTS = ['Title', 'Subtitle', 'Footer', 'Capitals note', 'States note',
  'Grammar', 'Sentence type', 'Tense pattern', 'Tip-offs note', 'Mythology note'];
var GUIDE_DEFAULTS = [
  ['Title', '', 'MAL Study Guide', ''],
  ['Subtitle', '', 'Mesa Academic League · Mesa Academy for Advanced Studies · 2026–27', ''],
  ['Footer', '', 'Mesa Academic League · Study Guide 2026–27', ''],
  ['Capitals note', 'Potential questions', 'name the five capitals beginning with A, the four beginning with B, the six beginning with C.', ''],
  ['States note', '', '“Sunshine State” is listed for both Florida and New Mexico. Both have a historical claim, but Florida’s is the official one.', ''],
  ['States note', '', 'North Dakota’s “Sioux State” is genuine but dated; Peace Garden State and Flickertail State are current.', ''],
  ['Grammar', 'Transitive verb', 'Requires a noun or pronoun to complete its meaning — answers who(m)? or what?', 'The students write essays.  (Without “essays” the sentence makes no sense.)'],
  ['Grammar', 'Intransitive verb', 'Does not require an object to complete its meaning — answers when, where, how or why.', 'The children sat.'],
  ['Grammar', 'Preposition', 'Shows how a noun or pronoun relates to other words in the sentence — usually time, distance or position: of, at, by, near, under, over, beside, among, between, down, along, behind, inside.  Note: the subject of a sentence may never come from a prepositional phrase.', 'The book sat near the lamp.'],
  ['Sentence type', 'Simple', 'One independent clause.', 'The children sat.'],
  ['Sentence type', 'Compound', 'Two or more independent clauses joined by a semicolon or a conjunction (and, but, or, so).', 'The children sat, but they were not happy.'],
  ['Sentence type', 'Complex', 'One independent clause and at least one dependent clause.', 'The children sat because they were told to.'],
  ['Sentence type', 'Compound-complex', 'At least two independent clauses and at least one dependent clause.', 'The children sat, but they got up before they were supposed to.'],
  ['Tense pattern', 'Continuous', '(be) + (verb) + ing', ''],
  ['Tense pattern', 'Perfect', '(have) + (verb)', ''],
  ['Tense pattern', 'Perfect continuous', '(have) + been + (verb) + ing', ''],
  ['Tip-offs note', '', 'Think super fast buzzing.', ''],
  ['Mythology note', '', 'Mars was more honored in Rome as a guardian of agriculture and the state, unlike the often disliked Ares.', ''],
  ['Mythology note', '', 'Apollo is the one god who kept the same name in both traditions.', '']
];
var GUIDE_NOTES = {
  Part: 'Which part of the study guide this row feeds. Rows of the same part print in this order.',
  Name: 'The bold label, where the part has one (a grammar term, a sentence type, a tense aspect).',
  Text: 'What prints. Text can use <b>bold</b> and <em>italics</em>.',
  Example: 'The example sentence, for Grammar and Sentence type rows.'
};

var CATEGORY_CODE = {
  'Algebra': 'AL', 'Geometry': 'GE', 'Logic': 'LG', 'Numbers': 'NE', 'Probability': 'PR',
  'Word Problems': 'WP', 'Current Events': 'CE', 'Economics': 'EC', 'US Geography': 'UG',
  'US Law': 'UL', 'US History': 'UH', 'World Geography': 'WG', 'World History': 'WH',
  'Language Arts': 'LA', 'Grammar': 'GR', 'Vocabulary': 'VC', 'Literature': 'LT',
  'Physical Sci': 'PS', 'Life Sci': 'LS', 'Earth Sci': 'ES', 'General Science': 'GS'
};
var LEGEND = [
  ['MATH', ['AL  Algebra', 'GE  Geometry', 'LG  Logic', 'NE  Numeric Expressions & Arithmetic',
    'PR  Probability, Permutations & Combinations', 'WP  Word Problems']],
  ['SOCIAL STUDIES', ['CE  Current Events', 'EC  Economics', 'UG  US Geography', 'UL  US Law',
    'UH  US History', 'WG  World Geography', 'WH  World History']],
  ['ENGLISH', ['LA  Language Arts', 'GR  Grammar', 'SP  Spelling', 'VC  Vocabulary', 'LT  Literature']],
  ['SCIENCE', ['PS  Physical Science', 'LS  Life Science', 'ES  Earth Science', 'GS  General Science']]
];
// A matching question carries its parallel lists in one sentence ("Cities: ...
// Countries: ..."); each list starts its own line. Same list as build_packet.py.
var LIST_LABELS = ['Countries', 'Country', 'Civilizations', 'Definitions', 'Constitution',
  'Amendments', 'New Name', 'Old Name', 'Cities', 'Areas', 'Time Periods', 'Events',
  'Inventions', 'Poets', 'Titles', 'Book', 'Books', 'Setting', 'Languages', 'Terms', 'Words',
  'Examples', 'Devices', 'National Parks', 'States', 'Landmarks', 'Cemeteries', 'Parks',
  'Homes', 'Animals', 'Fables', 'Specialty', 'Works', 'Cases', 'Rivers', 'Dictators',
  'Relationships', 'Rock type', 'Parent rock', 'Becomes', 'Monetary system'];

var CM = 28.3465;               // points
var GREY = '#555555';
var FONT = 'Calibri';

function regenerateStudyGuide() {
  guarded_('Regenerate study guide', function () {
    var ss = SpreadsheetApp.getActive();
    var ui = SpreadsheetApp.getUi();
    ss.toast('Reading the sheet…', 'Study guide', 30);
    var text = guideText_(ss);
    var data = guideData_(ss, text);
    var doc = guideDoc_(ui);
    if (!doc) return;
    ss.toast('Writing the study guide. This takes a minute…', 'Study guide', 180);
    doc.setName(text.one('Footer') ? plainText_(text.one('Footer')) : 'MAL Study Guide');
    renderGuide_(doc, data, text);
    var url = doc.getUrl();
    doc.saveAndClose();

    var lines = data.quarters.map(function (q) {
      return 'Quarter ' + q.n + ': ' + q.items.length + ' questions';
    });
    var html = '<div style="font:14px/1.45 Arial,sans-serif">' +
      '<p>The study guide now matches this sheet.</p>' +
      '<p><a href="' + escHtml_(url) + '" target="_blank" style="font-weight:bold">Open the study guide</a></p>' +
      '<p style="margin:0">' + lines.map(escHtml_).join('<br>') + '</p>' +
      (data.spelled ? '<p style="margin:6px 0 0">Spelling words are included in their quarters (' + data.spelled + ').</p>' : '') +
      (data.retired ? '<p style="margin:6px 0 0">' + data.retired + ' retired question' + (data.retired === 1 ? ' is' : 's are') + ' left out.</p>' : '') +
      (data.notes.length ? '<p style="margin:6px 0 0"><b>Worth a look:</b><br>• ' + data.notes.slice(0, 8).map(escHtml_).join('<br>• ') + '</p>' : '') +
      (text.created ? '<p style="margin:6px 0 0">A <b>' + GUIDE_TAB + '</b> tab was added to this sheet. Its grammar notes, footnotes and title print in the guide; edit them there.</p>' : '') +
      '<p style="color:#555;margin:10px 0 0">To hand out a Word file: in the document, File › Download › Microsoft Word.</p>' +
      '</div>';
    ui.showModalDialog(HtmlService.createHtmlOutput(html).setWidth(460).setHeight(330), 'Regenerate study guide');
  });
}

function escHtml_(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/** The document to write into: the one made last time, or a new one. */
function guideDoc_(ui) {
  var id = props_().getProperty('GUIDE_DOC_ID');
  if (id) {
    try {
      return DocumentApp.openById(id);
    } catch (e) {
      var again = ui.alert('Regenerate study guide',
        'The study guide document could not be opened. Either it was deleted, or it has ' +
        'not been shared with you (ask Mario to share it as an editor, then try again).\n\n' +
        'Make a brand-new study guide document instead?', ui.ButtonSet.YES_NO);
      if (again !== ui.Button.YES) return null;
    }
  }
  var doc = DocumentApp.create('MAL Study Guide');
  props_().setProperty('GUIDE_DOC_ID', doc.getId());
  return doc;
}

/** A tab as objects keyed by header, blank rows dropped. */
function rowsOf_(ss, name, need) {
  var sh = ss.getSheetByName(name);
  if (!sh) fail_('The "' + name + '" tab is missing, so the study guide can’t be built. Tabs can’t be renamed or deleted.');
  var grid = sh.getDataRange().getDisplayValues();
  var head = (grid[0] || []).map(function (h) { return String(h).trim(); });
  need.forEach(function (h) {
    if (head.indexOf(h) < 0) fail_('The "' + name + '" tab has no "' + h + '" column, so the study guide can’t be built.');
  });
  var out = [];
  for (var i = 1; i < grid.length; i++) {
    if (!grid[i].some(function (v) { return String(v).trim() !== ''; })) continue;
    var o = { row: i + 1 };
    head.forEach(function (h, j) { if (h) o[h] = String(grid[i][j] == null ? '' : grid[i][j]).trim(); });
    out.push(o);
  }
  return out;
}

/** The Study guide text tab, made and filled with the defaults on first use. */
function guideText_(ss) {
  var created = false;
  if (!ss.getSheetByName(GUIDE_TAB)) {
    var sh = ss.insertSheet(GUIDE_TAB);
    var cols = ['Part', 'Name', 'Text', 'Example'];
    var max = GUIDE_DEFAULTS.length + 100;
    if (sh.getMaxRows() < max) sh.insertRowsAfter(sh.getMaxRows(), max - sh.getMaxRows());
    sh.getRange(1, 1, sh.getMaxRows(), 4).setNumberFormat('@').setVerticalAlignment('top');
    var grid = [cols].concat(GUIDE_DEFAULTS).map(function (r) { return r.map(cell_); });
    sh.getRange(1, 1, grid.length, 4).setValues(grid);
    sh.getRange(1, 1, 1, 4).setFontWeight('bold').setBackground('#e8ecf3');
    sh.setFrozenRows(1);
    [130, 150, 520, 360].forEach(function (w, j) {
      sh.setColumnWidth(j + 1, w);
      sh.getRange(1, j + 1).setNote(GUIDE_NOTES[cols[j]]);
      sh.getRange(2, j + 1, sh.getMaxRows() - 1, 1).setWrap(j >= 2);
    });
    sh.getRange(2, 1, sh.getMaxRows() - 1, 1).setDataValidation(SpreadsheetApp.newDataValidation()
      .requireValueInList(GUIDE_PARTS, true).setAllowInvalid(false).build());
    created = true;
  }
  var rows = rowsOf_(ss, GUIDE_TAB, ['Part', 'Name', 'Text', 'Example']);
  return {
    created: created,
    all: function (part) { return rows.filter(function (r) { return r.Part === part; }); },
    one: function (part) {
      var r = rows.filter(function (x) { return x.Part === part; })[0];
      return r ? r.Text : '';
    }
  };
}

function firstQuarter_(s) {
  var m = String(s).match(/\d+/);
  return m ? parseInt(m[0], 10) : null;
}

/** Everything the guide prints, read from the tabs and put in print order. */
function guideData_(ss, text) {
  var notes = [];
  var qs = rowsOf_(ss, 'Questions', ['Retired', 'Quarter', 'Subject', 'Category', 'Level', 'Question', 'Answer']);
  var spell = rowsOf_(ss, 'Spelling', ['Word', 'Quarter', 'Level', 'Sentence']);
  var states = rowsOf_(ss, 'States', ['State', 'Capital', 'Nicknames', 'Motto']);
  var tips = rowsOf_(ss, 'Tip-offs', ['Question', 'Answer']);
  var tenses = rowsOf_(ss, 'Verb tenses', ['Tense', 'Formula', 'Example', 'Meaning']);
  var myth = rowsOf_(ss, 'Mythology', ['Greek', 'Roman', 'Domain']);

  var byQ = {};
  var retired = 0;
  function bucket(n) { return byQ[n] || (byQ[n] = { n: n, items: [] }); }
  qs.forEach(function (r) {
    if (!r.Question) return;
    if (/^(yes|y|x|true)$/i.test(r.Retired)) { retired++; return; }
    var n = firstQuarter_(r.Quarter);
    if (n === null) { notes.push('Questions row ' + r.row + ' has no quarter, so it is not in the guide.'); return; }
    var cat = CATEGORY_CODE[r.Category] || r.Category;
    // A question printed in two quarters is printed once, in the first.
    bucket(n).items.push({ code: r.Subject + '-' + cat + '-' + r.Level, q: r.Question, a: r.Answer, s: r.Subject });
  });

  // Each spelling word is its own question. A quarter's words print together,
  // straight after its last English question.
  var spelled = 0, words = {};
  spell.forEach(function (r) {
    var word = plainText_(r.Word);
    if (!word) return;
    var n = firstQuarter_(r.Quarter);
    if (n === null) { notes.push('Spelling row ' + r.row + ' has no quarter, so it is not in the guide.'); return; }
    var q = r.Sentence
      ? 'Say and spell the word “' + word + '” as it is used in the following sentence: “' + r.Sentence + '”'
      : 'Say and spell the word “' + word + '.”';
    (words[n] = words[n] || []).push({ code: 'EN-SP-' + r.Level, q: q, s: 'EN',
      a: word.toLowerCase().split(' ').map(function (w) { return w.split('').join('-'); }).join(' ') });
    spelled++;
  });
  Object.keys(words).forEach(function (n) {
    var items = bucket(Number(n)).items, at = -1;
    items.forEach(function (x, i) { if (x.s === 'EN') at = i; });
    Array.prototype.splice.apply(items, [at + 1, 0].concat(words[n]));
  });

  var quarters = Object.keys(byQ).map(Number).sort(function (a, b) { return a - b; })
    .map(function (n) { return byQ[n]; });
  quarters.forEach(function (q) { q.items.forEach(function (x, i) { x.n = i + 1; }); });

  return {
    quarters: quarters, retired: retired, spelled: spelled, notes: notes,
    capitals: states.filter(function (r) { return r.State && r.Capital; })
      .map(function (r) { return [r.State, r.Capital]; }),
    states: states.filter(function (r) { return r.State; })
      .map(function (r) { return [r.State, r.Nicknames, r.Motto]; }),
    tips: tips.filter(function (r) { return r.Question; }).map(function (r) { return [r.Question, r.Answer]; }),
    tenses: tenses.filter(function (r) { return r.Tense; }),
    myth: myth.filter(function (r) { return r.Greek; }).map(function (r) { return [r.Domain, r.Greek, r.Roman]; })
  };
}

// ----------------------------------------------------------- text and markup

var ENTITIES = {
  amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', rarr: '→', larr: '←',
  mdash: '—', ndash: '–', hellip: '…', lsquo: '‘', rsquo: '’', ldquo: '“', rdquo: '”',
  times: '×', divide: '÷', minus: '−', deg: '°', frac12: '½', frac14: '¼', frac34: '¾',
  eacute: 'é', middot: '·', sup2: '²', sup3: '³', pi: 'π', le: '≤', ge: '≥', ne: '≠'
};

/** Sheet text with its <b>/<em> markup read into bold and italic spans. */
function rich_(s) {
  s = String(s == null ? '' : s);
  var out = '', bold = [], ital = [], b = 0, it = 0, bAt = 0, iAt = 0;
  var re = /<(\/?)(b|strong|i|em|br)\b[^>]*>|<\/?[a-z][^>]*>|&(#x[0-9a-f]+|#\d+|[a-z0-9]+);/gi;
  var last = 0, m;
  while ((m = re.exec(s))) {
    out += s.slice(last, m.index);
    last = re.lastIndex;
    if (m[3]) {
      var e = m[3];
      if (e[0] === '#') {
        var code = e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
        out += String.fromCharCode(code);
      } else {
        out += ENTITIES.hasOwnProperty(e) ? ENTITIES[e] : m[0];
      }
      continue;
    }
    var tag = (m[2] || '').toLowerCase(), close = m[1] === '/';
    if (tag === 'br') { out += ' '; continue; }
    if (tag === 'b' || tag === 'strong') {
      if (!close && b++ === 0) bAt = out.length;
      if (close && b > 0 && --b === 0 && out.length > bAt) bold.push([bAt, out.length]);
    } else if (tag === 'i' || tag === 'em') {
      if (!close && it++ === 0) iAt = out.length;
      if (close && it > 0 && --it === 0 && out.length > iAt) ital.push([iAt, out.length]);
    }
  }
  out += s.slice(last);
  if (b > 0 && out.length > bAt) bold.push([bAt, out.length]);
  if (it > 0 && out.length > iAt) ital.push([iAt, out.length]);
  return { text: out, bold: bold, ital: ital };
}

function plainText_(s) { return rich_(s).text; }

var LIST_RE = new RegExp('\\s+(?=(?:' + LIST_LABELS.slice().sort(function (a, b) { return b.length - a.length; })
  .map(function (x) { return x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }).join('|') + '):)', 'g');

/** Each parallel list on its own line, but only after the stem's first colon. */
function breakLists_(text) {
  var i = text.indexOf(':');
  if (i < 0) return [text];
  var tail = text.slice(i + 1).replace(LIST_RE, '\n');
  return (text.slice(0, i + 1) + tail).split('\n');
}

// -------------------------------------------------------------- the document

function Guide_(body) {
  this.body = body;
  this.fresh = true;
}

/** A paragraph with spacing and a hanging indent, sizes in points. */
Guide_.prototype.para = function (runs, f) {
  f = f || {};
  var p;
  if (this.fresh) {
    p = firstPara_(this.body);
    this.fresh = false;
  } else {
    p = this.body.appendParagraph(' ');   // Docs refuses an empty text element
  }
  p.setHeading(DocumentApp.ParagraphHeading.NORMAL)
    .setAlignment(f.align || DocumentApp.HorizontalAlignment.LEFT)
    .setLineSpacing(1)
    .setSpacingBefore(f.before || 0)
    .setSpacingAfter(f.after === undefined ? 2 : f.after)
    .setIndentStart(f.indent || 0)
    .setIndentFirstLine((f.indent || 0) - (f.hang || 0));
  writeRuns_(p, runs);
  return p;
};

Guide_.prototype.heading = function (label, size, before) {
  return this.para([[label, { bold: true, size: size || 12 }]],
    { before: before === undefined ? 10 : before, after: 4 });
};

Guide_.prototype.pageBreak = function () {
  this.body.appendPageBreak();
};

/** A table: widths in cm, an optional grey header row, cells as run lists or strings. */
Guide_.prototype.table = function (widths, header, rows, f) {
  f = f || {};
  var all = (header ? [header] : []).concat(rows);
  // Built row by row with a placeholder space in every cell: Docs refuses an
  // empty text element, and appendTable([['', ...]]) is one.
  var t = this.body.appendTable();
  all.forEach(function (r) {
    var tr = t.appendTableRow();
    r.forEach(function () { tr.appendTableCell(' '); });
  });
  t.setBorderWidth(f.borderless ? 0 : 0.5).setBorderColor(f.borderless ? '#ffffff' : '#000000');
  widths.forEach(function (w, j) { t.setColumnWidth(j, w * CM); });
  all.forEach(function (r, i) {
    r.forEach(function (c, j) {
      var cell = t.getCell(i, j);
      cell.setPaddingTop(f.pad || 1).setPaddingBottom(f.pad || 1).setPaddingLeft(4).setPaddingRight(4);
      var runs = typeof c === 'string' ? [[c, { size: f.size || 8.5 }]] : c;
      if (header && i === 0) {
        cell.setBackgroundColor('#e8e8e8');
        runs = runs.map(function (x) { return [x[0], merge_(x[1], { bold: true })]; });
      }
      var p = firstPara_(cell);
      p.setSpacingBefore(0).setSpacingAfter(0).setLineSpacing(1);
      writeRuns_(p, runs.map(function (x) { return [x[0], merge_({ size: f.size || 8.5 }, x[1])]; }));
    });
  });
  return t;
};

/** The paragraph a cleared body, footer or new cell keeps, or a new one. */
function firstPara_(container) {
  if (container.getNumChildren() && container.getChild(0).getType() === DocumentApp.ElementType.PARAGRAPH) {
    return container.getChild(0).asParagraph();
  }
  return container.appendParagraph(' ');
}

function merge_(a, b) {
  var o = {};
  [a || {}, b || {}].forEach(function (x) { for (var k in x) o[k] = x[k]; });
  return o;
}

/** Set a paragraph's text in one go, then style ranges of it. Styling a whole
 *  run returned by appendText is unreliable: Docs merges neighbouring runs. */
function writeRuns_(p, runs) {
  var text = '', marks = [];
  runs.forEach(function (r) {
    var rc = rich_(r[0]);
    var t = rc.text.replace(/\s*\n\s*/g, ' ');
    marks.push({ s: text.length, e: text.length + t.length, st: r[1] || {}, rc: rc });
    text += t;
  });
  // An empty run list leaves the paragraph as it is (blank, or the placeholder
  // space); setting empty text is what Docs refuses.
  if (!text.length) return;
  p.setText(text);
  var tx = p.editAsText();
  tx.setFontFamily(FONT).setFontSize(9.5).setBold(false).setItalic(false).setForegroundColor('#000000');
  marks.forEach(function (m) {
    if (m.e <= m.s) return;
    var st = m.st, a = m.s, z = m.e - 1;
    if (st.size && st.size !== 9.5) tx.setFontSize(a, z, st.size);
    if (st.bold) tx.setBold(a, z, true);
    if (st.italic) tx.setItalic(a, z, true);
    if (st.color) tx.setForegroundColor(a, z, st.color);
    m.rc.bold.forEach(function (x) { if (x[1] > x[0]) tx.setBold(a + x[0], Math.min(z, a + x[1] - 1), true); });
    m.rc.ital.forEach(function (x) { if (x[1] > x[0]) tx.setItalic(a + x[0], Math.min(z, a + x[1] - 1), true); });
  });
}

function renderGuide_(doc, data, text) {
  var body = doc.getBody();
  body.clear();
  body.setPageWidth(612).setPageHeight(792)                      // US Letter
    .setMarginTop(1.5 * CM).setMarginBottom(1.5 * CM)
    .setMarginLeft(1.3 * CM).setMarginRight(1.3 * CM);
  var footer = doc.getFooter() || doc.addFooter();
  footer.clear();
  var fp = firstPara_(footer);
  fp.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  writeRuns_(fp, [[text.one('Footer'), { size: 8, color: GREY }]]);

  var g = new Guide_(body);
  g.para([[text.one('Title') || 'MAL Study Guide', { bold: true, size: 20 }]], { after: 1 });
  g.para([[text.one('Subtitle'), { color: GREY }]], { after: 8 });

  // --- legend
  g.heading('Category codes', 12, 0);
  var depth = Math.max.apply(null, LEGEND.map(function (x) { return x[1].length; }));
  var legend = [];
  for (var i = 0; i < depth; i++) legend.push(LEGEND.map(function (x) { return x[1][i] || ''; }));
  g.table([5.3, 4.5, 3.6, 4.1], LEGEND.map(function (x) { return x[0]; }), legend);

  // --- capitals, two columns, alphabetical by city
  g.heading('State capitals, alphabetically by city', 12);
  var caps = data.capitals.slice().sort(function (a, b) { return a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0; });
  var groups = {};
  caps.forEach(function (c) { var k = c[1].charAt(0).toUpperCase(); (groups[k] = groups[k] || []).push(c[1]); });
  // A letter marks only the first capital of a run of three or more.
  function tag(cap) {
    var k = cap.charAt(0).toUpperCase();
    return groups[k] && groups[k].length >= 3 && groups[k][0] === cap ? k : '';
  }
  var half = Math.ceil(caps.length / 2), capRows = [];
  for (i = 0; i < half; i++) {
    var a = caps[i], b = caps[i + half];
    capRows.push([[[tag(a[1]), { bold: true }]], a[1], a[0],
      [[b ? tag(b[1]) : '', { bold: true }]], b ? b[1] : '', b ? b[0] : '']);
  }
  g.table([0.8, 3.9, 3.0, 0.8, 3.9, 3.1], ['', 'Capital', 'State', '', 'Capital', 'State'], capRows);
  var big = Object.keys(groups).sort().filter(function (k) { return groups[k].length >= 4; })
    .map(function (k) { return groups[k].length + ' with ' + k; }).join(', ');
  var capNote = text.all('Capitals note');
  if (capNote.length || big) {
    g.para([[(capNote[0] && capNote[0].Name) || 'Potential questions', { bold: true, size: 8.5 }], [':', { bold: true, size: 8.5 }]], { before: 3, after: 0 });
    capNote.forEach(function (r) { g.para([[r.Text, { italic: true, size: 8.5 }]], { indent: 0.5 * CM, after: 0 }); });
    if (big) g.para([['Memorize any group of four or more — ' + big + '.', { italic: true, size: 8.5 }]], { indent: 0.5 * CM, after: 0 });
  }

  // --- nicknames and mottos: fifty rows, a page of their own
  g.pageBreak();
  g.heading('State nicknames and mottos', 12, 0);
  g.table([3.0, 7.0, 7.5], ['State', 'Nickname(s)', 'Motto'], data.states.map(function (r) {
    return [r[0], r[1], [[r[2], { italic: true }]]];
  }), { pad: 0.5 });
  text.all('States note').forEach(function (r) {
    g.para([['Note: ' + r.Text, { italic: true, size: 8, color: GREY }]], { before: 2, after: 0 });
  });

  // --- grammar
  g.heading('Grammar', 12, 8);
  text.all('Grammar').forEach(function (r) {
    g.para([[r.Name, { bold: true }]], { before: 4, after: 1 });
    if (r.Text) g.para([[r.Text, { size: 9 }]], { indent: 0.5 * CM, after: 1 });
    if (r.Example) g.para([['e.g.  ' + r.Example, { size: 9, italic: true }]], { indent: 0.5 * CM, after: 2 });
  });
  var types = text.all('Sentence type');
  if (types.length) {
    g.para([['The four sentence types', { bold: true }]], { before: 6, after: 1 });
    types.forEach(function (r) {
      g.para([[r.Name + ' — ', { bold: true, size: 9 }], [r.Text, { size: 9 }]], { indent: 1.0 * CM, hang: 0.5 * CM, after: 0 });
      if (r.Example) g.para([[r.Example, { size: 9, italic: true }]], { indent: 1.0 * CM, after: 2 });
    });
  }

  // --- the twelve verb tenses, as a grid when every name reads "<aspect> <time>"
  if (data.tenses.length) {
    g.heading(data.tenses.length === 12 ? 'The twelve verb tenses' : 'The verb tenses', 12, 10);
    var times = ['Past', 'Present', 'Future'], aspects = [], grid = {}, flat = false;
    data.tenses.forEach(function (r) {
      var words = plainText_(r.Tense).trim().split(/\s+/);
      var t = words.filter(function (w) { return /^(past|present|future)$/i.test(w); });
      if (t.length !== 1) { flat = true; return; }
      var time = t[0].charAt(0).toUpperCase() + t[0].slice(1).toLowerCase();
      var aspect = words.filter(function (w) { return w !== t[0]; }).join(' ').toLowerCase() || 'simple';
      if (aspects.indexOf(aspect) < 0) aspects.push(aspect);
      var key = aspect + '|' + time;
      if (grid[key]) flat = true;
      grid[key] = r;
    });
    if (!flat) {
      var patterns = {};
      text.all('Tense pattern').forEach(function (r) { patterns[r.Name.toLowerCase()] = r.Text; });
      var trows = [];
      aspects.forEach(function (asp) {
        var cell = function (time, field, st) {
          var r = grid[asp + '|' + time];
          return [[r ? r[field] : '', st || {}]];
        };
        trows.push([[[asp.toUpperCase(), { bold: true }], [patterns[asp] ? '  ' + patterns[asp] : '', { size: 8, color: GREY }]]]
          .concat(times.map(function (t) { return cell(t, 'Meaning'); })));
        trows.push([[['Formula', { italic: true, color: GREY }]]].concat(times.map(function (t) { return cell(t, 'Formula', { italic: true }); })));
        trows.push([[['Example', { italic: true, color: GREY }]]].concat(times.map(function (t) { return cell(t, 'Example'); })));
      });
      g.table([3.4, 5.1, 5.1, 5.2], [''].concat(times), trows);
    } else {
      data.notes.push('A verb tense name does not read like “Past perfect”, so the tenses print as a list, not a grid.');
      g.table([4.0, 3.8, 5.0, 6.0], ['Tense', 'Formula', 'Example', 'Meaning'], data.tenses.map(function (r) {
        return [[[r.Tense, { bold: true }]], [[r.Formula, { italic: true }]], r.Example, r.Meaning];
      }));
    }
  }

  // --- tip-offs
  g.heading('Tip-off questions', 12, 12);
  text.all('Tip-offs note').forEach(function (r) {
    g.para([[r.Text, { italic: true, size: 8.5, color: GREY }]], { after: 4 });
  });
  g.table([1.0, 12.4, 5.5], null, data.tips.map(function (r, i) {
    return [[[(i + 1) + '.', { bold: true }]], r[0], [[r[1], { bold: true }]]];
  }), { borderless: true, size: 9, pad: 1.5 });

  // --- the questions, a page break before each quarter
  data.quarters.forEach(function (q) {
    g.pageBreak();
    g.heading('Quarter ' + q.n, 14, 0);
    q.items.forEach(function (x) {
      var lines = breakLists_(x.q);
      lines.forEach(function (line, j) {
        var runs = [];
        if (j === 0) {
          runs.push([x.n + '.  ', { bold: true, size: 9, color: GREY }]);
          runs.push([x.code + '  ', { bold: true, size: 9 }]);
        }
        runs.push([line, { size: 10 }]);
        if (j === lines.length - 1) runs.push(['  (' + x.a + ')', { bold: true, size: 10 }]);
        g.para(runs, j === 0 ? { indent: 1.5 * CM, hang: 1.5 * CM, after: lines.length > 1 ? 0 : 3 }
          : { indent: 1.5 * CM, after: j === lines.length - 1 ? 3 : 0 });
      });
    });
  });

  // --- mythology flows on from the last quarter: no near-empty final sheet
  if (data.myth.length) {
    g.heading('Mythology', 12, 8);
    g.table([7.0, 5.0, 5.5], ['Domain', 'Greek', 'Roman'], data.myth, { pad: 0.5 });
    text.all('Mythology note').forEach(function (r) {
      g.para([['Note: ' + r.Text, { italic: true, size: 8, color: GREY }]], { before: 2, after: 0 });
    });
  }
}
