/* Makes the Knowledge Engine's bug-report form. Run it once:
   1. Open https://script.new (signed in as the account that should own the form).
   2. Paste this file over the sample code, save, and run makeBugForm.
   3. Allow it to manage your forms when Google asks.
   4. Copy the PREFILL line from the execution log and send it back; it goes in
      BUG_FORM in game/engine_src.html. The game swaps __DETAILS__ for the
      student's question, browser and screen, so nobody has to type them.
   The responses go to a new sheet beside the form; change that in the form's
   Responses tab if you want them somewhere else. */
function makeBugForm() {
  const form = FormApp.create('Knowledge Engine: report a problem');
  form.setDescription('Something broken, wrong or confusing in the Knowledge Engine? Tell us here. ' +
    'The Details box at the bottom is filled in by the game; leave it as it is.');
  form.setCollectEmail(false);
  form.setAllowResponseEdits(false);
  form.setLimitOneResponsePerUser(false);
  form.setConfirmationMessage('Thanks! Your report was sent. You can close this tab and get back to the engine.');

  form.addMultipleChoiceItem()
    .setTitle('What kind of problem?')
    .setChoiceValues([
      'Something is broken (a button, a gear, the page)',
      'A question or answer is wrong',
      'Something looks wrong on my screen',
      'Something is confusing',
      'An idea to make it better',
    ])
    .showOtherOption(true)
    .setRequired(true);

  form.addParagraphTextItem()
    .setTitle('What happened?')
    .setHelpText('What did you expect, and what did you see instead? If it is a question, which one?')
    .setRequired(true);

  form.addParagraphTextItem()
    .setTitle('What were you doing right before it happened?')
    .setRequired(false);

  form.addTextItem()
    .setTitle('Your name (optional)')
    .setHelpText('Only if you are happy for us to ask you about it.')
    .setRequired(false);

  const details = form.addParagraphTextItem()
    .setTitle('Details (filled in by the game)')
    .setHelpText('Which question was on screen, your browser and your screen size. Nothing personal.')
    .setRequired(false);

  const ss = SpreadsheetApp.create('Knowledge Engine: problem reports');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());

  const prefill = form.createResponse()
    .withItemResponse(details.createResponse('__DETAILS__'))
    .toPrefilledUrl();

  Logger.log('EDIT:    ' + form.getEditUrl());
  Logger.log('SHEET:   ' + ss.getUrl());
  Logger.log('PREFILL: ' + prefill);
}
