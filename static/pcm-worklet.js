class PcmDownsampleProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.inputSampleRate = sampleRate;
    this.targetSampleRate = 16000;
    this.ratio = this.inputSampleRate / this.targetSampleRate;
    this.sourceBuffer = [];
    this.outputBuffer = [];
    this.frameSize = 512;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) {
      return true;
    }

    const channel = input[0];
    for (let i = 0; i < channel.length; i += 1) {
      this.sourceBuffer.push(channel[i]);
    }

    while (this.sourceBuffer.length >= this.ratio) {
      const sample = this.sourceBuffer[0];
      this.outputBuffer.push(Math.max(-1, Math.min(1, sample)));
      this.sourceBuffer.splice(0, Math.floor(this.ratio));
    }

    while (this.outputBuffer.length >= this.frameSize) {
      const frame = this.outputBuffer.splice(0, this.frameSize);
      const pcm = new Int16Array(frame.length);
      for (let i = 0; i < frame.length; i += 1) {
        pcm[i] = frame[i] < 0 ? frame[i] * 32768 : frame[i] * 32767;
      }
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
    }

    return true;
  }
}

registerProcessor("pcm-downsample", PcmDownsampleProcessor);
