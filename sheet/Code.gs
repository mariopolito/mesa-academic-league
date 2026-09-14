/**
 * Mesa Academic League study site -- the content sheet's publish button.
 *
 * Paste this whole file into the sheet's Extensions > Apps Script editor, save,
 * and reload the sheet. A "Study site" menu appears:
 *
 *   Publish to site          commits the sheet to content/content.json in the
 *                            GitHub repo; a GitHub Action checks it, rebuilds
 *                            index.html, and this reports back what happened.
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
