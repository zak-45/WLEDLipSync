/* 

author:	zak45
date:	19/11/2024
version:1.0.0
WS server
WLEDLipSync version

*/

var isInit = True;
var spleeterModule = "";

function init() {
	script.log("-- Custom command called init()");
	spleeterModule = root.modules.getItemWithName("Spleeter");
	if (spleeterModule == 'undefined') {
	    script.log('Spleeter module does not exist');
	    util.showMessageBox("Lipsync", "Spleeter Module not present ...", "error", "ok");
	}
}

/**
 * Handles incoming WebSocket messages.
 *
 * This function is triggered when a message is received from a WebSocket client.
 * It logs the received message for debugging or informational purposes.
 *
 * @param {Object} client - The WebSocket client that sent the message.
 * @param {string} message - The message content received from the client.
 */
function wsMessageReceived(client, message) {
    script.log("Message received: " + message + " from : " + client);
    AnalyseMessage(message);
}

/**
 * Analyzes a JSON message.
 *
 * This function parses a JSON-formatted message and performs analysis on its contents.
 * It expects the message to be a valid JSON string.
 *
 * @param {string} message - The JSON string to be parsed and analyzed.
 */
function AnalyseMessage(message) {

    var parsedMessage = JSON.parse(message);

    // Perform analysis on parsedMessage here
    if (parsedMessage.action == 'undefined' ||
        parsedMessage.action.type == 'undefined' ||
        parsedMessage.action.param == 'undefined' ) {

            script.log ('error in Json');
            return;
    }

    script.log('Execute action: ' + parsedMessage.action.type);

    if (parsedMessage.action.type == 'init_cha'){
        script.log('init connection');
	    util.showMessageBox("Lipsync", "Chataigne <--> WLEDLipSync", "info", "ok");
        return;
    }
    if (parsedMessage.action.type == 'runSpleeter'){
        script.log('Run Spleeter for : ' + parsedMessage.action.param.fileName);

		var cmd = spleeterModule.commandTester.setCommand("Spleeter","Spleeter","Separate");
		cmd.fileName.set(parsedMessage.action.param.fileName);
		spleeterModule.commandTester.trigger.trigger();
    }

}

// used for value/expression testing .......
function testScript(songname) {
	script.log("test");
}
