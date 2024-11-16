import WaveSurfer from '/assets/js/wavesurfer.esm.js';
import TimelinePlugin from '/assets/js/wave_plugins/timeline.esm.js';
import RegionsPlugin from '/assets/js/wave_plugins/regions.esm.js'

let wavesurfer;
let cuePoints = [];
let checkBlinkingInterval;

// Initialize the Regions plugin
let regions = RegionsPlugin.create()

// Give regions a random color when they are created
let random = (min, max) => Math.random() * (max - min) + min
let randomColor = () => `rgba(${random(0, 255)}, ${random(0, 255)}, ${random(0, 255)}, 0.5)`

// init waveform at page load only so container exist
document.addEventListener('DOMContentLoaded', function() {
    initializeWavesurfer();
});

// Function to load the JSON file and create markers
window.LoadMouthCues = async function (JsonFile) {
    if (waveform) {
        try {
            const response = await fetch(JsonFile);
            const data = await response.json(); // Parse the JSON data
            // Create regions for each mouth cue
            data.mouthCues.forEach(cue => {
                regions.addRegion({
                    start:cue.start,
                    content:cue.value,
                    color:randomColor()
                });
            });
        } catch (error) {
            console.error('Error loading the JSON file:', error);
        }
    }
}

// create a marker from GUI
window.add_marker = function(time, letter) {
    if (wavesurfer) {
        regions.addRegion({
        start: time,
        content: letter,
        color: randomColor()
        });
    };
};

// clean all markers from GUI
window.clear_markers = async function() {
    if (wavesurfer) {
        regions.clearRegions();
    };
};

// generate cue data from GUI
window.genCueData = async function() {
    // Check container exist
    checkCuePointsAreaExistence(10000, 500).then((found) => {
        if (found) {
            // console.log('CuePointsArea exists!');
            cuePoints = generateCuePointsFromContainer('CuePoints');
            // console.log(`Number of cue points generated: ${cuePoints.length}`);
        } else {
            // console.log('CuePointsArea does not exist.');
        }
    });
};

/**
 * Generates an array of cue points from the specified container element.
 *
 * This function retrieves all elements with the class 'cue-point' within the
 * specified container and constructs an array of cue point objects. Each object
 * contains the cue point's time, ID, and the corresponding DOM element.
 *
 * @param {string} containerId - The ID of the container element from which to retrieve cue points.
 * @returns {Array<Object>} An array of cue point objects, each containing the time, ID, and element.
 * @returns {number} return.time - The time associated with the cue point, parsed as a float.
 * @returns {string} return.id - The ID of the cue point element.
 * @returns {Element} return.element - The DOM element representing the cue point.
 */
function generateCuePointsFromContainer(containerId) {
    const container = document.getElementById(containerId);
    if (!container) {
        return [];
    }
    const cuePointElements = container.querySelectorAll('.cue-point');
    return Array.from(cuePointElements).map(cueElement => {
        const timeString = cueElement.id;
        return {
            time: parseFloat(timeString),
            id: timeString,
            element: cueElement
        };
    });
}

/**
 * Checks for the existence of the CuePointsArea element within the CardMouth element.
 *
 * This function repeatedly checks for the presence of the CuePointsArea element
 * inside the CardMouth element until either the element is found or the specified
 * duration is exceeded. It returns a promise that resolves to true if the element
 * is found, and false if the duration is exceeded without finding the element.
 *
 * @param {number} [duration=5000] - The maximum time to wait for the element to appear, in milliseconds.
 * @param {number} [interval=100] - The interval between checks, in milliseconds.
 * @returns {Promise<boolean>} A promise that resolves to true if the CuePointsArea is found, otherwise false.
 */
function checkCuePointsAreaExistence(duration = 5000, interval = 100) {
    return new Promise((resolve) => {
        const startTime = Date.now();
        const checkInterval = setInterval(() => {
            const elapsedTime = Date.now() - startTime;
            // Check if the duration has been exceeded
            if (elapsedTime > duration) {
                clearInterval(checkInterval);
                // console.log('Time duration exceeded without finding the element.');
                resolve(false);
                return;
            }
            // Check if the CuePointsArea exists inside the CardMouth
            const cardMouth = document.getElementById('CardMouth');
            if (cardMouth) {
                const cuePointsArea = cardMouth.querySelector('#CuePointsArea');
                if (cuePointsArea) {
                    clearInterval(checkInterval);
                    // console.log('CuePointsArea found.');
                    resolve(true);
                    return;
                }
            }
            // console.log('Checking for CuePointsArea...');
        }, interval);
    });
}

/**
 * Finds the nearest cue point to a specified time within a threshold.
 *
 * This function iterates through the available cue points and determines
 * which cue point is closest to the given time, provided that the difference
 * is within a specified threshold. If no cue points are found or if none
 * are within the threshold, it returns null.
 *
 * @param {number} time - The time to which the nearest cue point is to be found.
 * @returns {Object|null} The nearest cue point object if found within the threshold, otherwise null.
 * @returns {number} return.time - The time associated with the cue point.
 * @returns {string} return.id - The ID of the cue point.
 * @returns {Element} return.element - The DOM element representing the cue point.
 */
function findNearestCuePoint(time) {
    if (cuePoints.length === 0) {
        return null;
    }
    const threshold = 1;
    let nearestCue = null;
    let smallestDiff = Infinity;
    cuePoints.forEach(cue => {
        const diff = Math.abs(time - cue.time);
        if (diff < smallestDiff && diff < threshold) {
            smallestDiff = diff;
            nearestCue = cue;
        }
    });
    return nearestCue;
}

/**
 * Checks and updates the visual state of cue points based on the current playback time.
 *
 * This function retrieves the current playback time from the Wavesurfer instance and
 * iterates through the defined cue points. If the current time is within a specified
 * threshold of a cue point's time, it adds a 'blink' class to the corresponding DOM element;
 * otherwise, it removes the class to indicate that the cue point is not active.
 *
 * @returns {void} This function does not return a value.
 */
function checkCuePoints() {
    const currentTime = wavesurfer.getCurrentTime();
    const threshold = 5;
    cuePoints.forEach(cue => {
        const cueElement = document.getElementById(cue.id);
        if (cueElement) {
            if (Math.abs(currentTime - cue.time) < threshold) {
                cueElement.classList.add('blink');
            } else {
                cueElement.classList.remove('blink');
            }
        }
    });
}

/**
 * Initializes the Wavesurfer instance and sets up event listeners for audio playback.
 *
 * This function creates a Wavesurfer instance linked to a specified audio element and
 * configures it with various plugins and settings. It also establishes event listeners
 * to synchronize playback between the audio element and the Wavesurfer instance, as well
 * as handling user interactions with the waveform for seeking and cue point highlighting.
 *
 * @returns {void} This function does not return a value.
 */
function initializeWavesurfer() {
    const audioElement = document.getElementById('player_vocals');
    audioElement.onloadeddata = (event) => {
        if (wavesurfer) {
            wavesurfer.destroy()
        }
        // Wavesurfer
        wavesurfer = WaveSurfer.create({
            container: '#waveform',
            waveColor: 'violet',
            progressColor: 'purple',
            plugins: [TimelinePlugin.create({
                      height: 20,
                      insertPosition: 'beforebegin',
                      timeInterval: 0.2,
                      primaryLabelInterval: 5,
                      secondaryLabelInterval: 1,
                      style: {
                        fontSize: '10px',
                        color: 'yellow',
                        background: '#0E7490',
                      },
                    }), regions],
        });
        // console.log(audioElement.src)
        // put volume to zero, not used to play any sound
        wavesurfer.load(audioElement.src);
        wavesurfer.setVolume(0);
        // zoom
        wavesurfer.once('decode', () => {
          document.querySelector('input[type="range"]').oninput = (e) => {
            const minPxPerSec = Number(e.target.value)
            wavesurfer.zoom(minPxPerSec)
          }
        });
        // events to sync with GUI audio player
        audioElement.addEventListener('play', function() {
            wavesurfer.play();
        });
        audioElement.addEventListener('pause', function() {
            wavesurfer.pause();
        });
        audioElement.addEventListener('seeked', function() {
            wavesurfer.seekTo(audioElement.currentTime / audioElement.duration);
        });
        audioElement.addEventListener('timeupdate', function() {
            if (Math.abs(wavesurfer.getCurrentTime() - audioElement.currentTime) > 0.1) {
                wavesurfer.seekTo(audioElement.currentTime);
            }
        });
        // click on waveform will blink nearest UI card
        document.getElementById('waveform').addEventListener('click', function(e) {
            const waveformWidth = this.clientWidth;
            const clickPosition = e.offsetX;
            const progress = clickPosition / waveformWidth;
            const newTime = (progress * audioElement.duration).toFixed(2);
            audioElement.currentTime = parseFloat(newTime);
            wavesurfer.seekTo(progress);
            // console.log(newTime);
            const nearestCue = findNearestCuePoint(newTime);
            if (nearestCue) {
                cuePoints.forEach(cue => {
                    const cueElement = document.getElementById(cue.id);
                    if (cueElement) {
                    cueElement.classList.remove('blink');
                    }
                });
                // console.log(nearestCue);
                nearestCue.element.classList.add('blink');
                const selectCue = document.getElementById(nearestCue.id)
                if (selectCue) {
                    selectCue.focus({  preventScroll: false , focusVisible: true })
                    selectCue.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" })
                }
            } else {
                // console.log('not found nearest');
            }
        });
    };
    // in case of any audio element error, waveform is cleared
    audioElement.addEventListener('error', function() {
        if (wavesurfer) {
            wavesurfer.empty();
        }
    });
}
