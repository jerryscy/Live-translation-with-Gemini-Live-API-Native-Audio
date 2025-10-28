class AudioProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
    }

    process(inputs, outputs, parameters) {
        const input = inputs[0];
        if (input.length > 0) {
            const pcmData = new Int16Array(input[0].length);
            for (let i = 0; i < input[0].length; i++) {
                let s = Math.max(-1, Math.min(1, input[0][i]));
                s = s < 0 ? s * 0x8000 : s * 0x7FFF;
                pcmData[i] = s;
            }
            this.port.postMessage(pcmData.buffer, [pcmData.buffer]);
        }
        return true;
    }
}

registerProcessor('audio-processor', AudioProcessor);
