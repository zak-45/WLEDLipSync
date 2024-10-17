    <script type="module">
        import WaveSurfer from 'https://unpkg.com/wavesurfer.js/dist/wavesurfer.esm.js';
        import TimelinePlugin from 'https://unpkg.com/wavesurfer.js/dist/plugins/timeline.esm.js';

        let wavesurfer;
        let cuePoints = [];
        let checkBlinkingInterval;

        const bottomTimeline = TimelinePlugin.create({
          height: 10,
          timeInterval: 5,
          primaryLabelInterval: 1,
          style: {
            fontSize: '8px',
            color: '#6A3274',
          },
        });

        async function generateCuePointsFromContainer(containerId) {
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

        window.genCueData = async function() {
            cuePoints = await generateCuePointsFromContainer('CuePoints');
            // console.log(`Number of cue points generated: ${cuePoints.length}`);
        };

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

        function checkCuePoints() {
            const currentTime = wavesurfer.getCurrentTime();
            const threshold = 1;

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

        async function initializeWavesurfer() {
            const audioElement = document.getElementById('player_vocals');
            audioElement.addEventListener('loadeddata', async function() {
                if (wavesurfer) {
                    wavesurfer.destroy();
                }

                wavesurfer = WaveSurfer.create({
                    container: '#waveform',
                    waveColor: 'violet',
                    progressColor: 'purple',
                    backend: 'MediaElement',
                    plugins: [bottomTimeline],
                });

                await wavesurfer.load(audioElement.src);
                wavesurfer.setVolume(0);

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
                            cueElement.classList.remove('blink');
                        });
                        // console.log(nearestCue);
                        nearestCue.element.classList.add('blink');
                        const selectCue = document.getElementById(nearestCue.id)
                        selectCue.focus({  preventScroll: false , focusVisible: true })
                        selectCue.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" })

                    } else {
                        // console.log('not found nearest');
                    }
                });
            });

            audioElement.addEventListener('error', function() {
                if (wavesurfer) {
                    wavesurfer.empty();
                }
            });
        }

        document.addEventListener('DOMContentLoaded', function() {
            initializeWavesurfer();
        });

        function refresh_waveform(fileName) {
            const newSrc = fileName;
            updateAudioSource(newSrc);
        }

        async function updateAudioSource(newSrc) {
            const audioElement = document.getElementById('audio');
            audioElement.src = newSrc;
            await audioElement.load();
            initializeWavesurfer();
        }
    </script>
