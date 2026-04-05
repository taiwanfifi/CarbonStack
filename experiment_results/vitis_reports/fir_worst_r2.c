// FIR filter - worst pragma config (PIPELINE OFF)
#define N 128
#define TAPS 16

void fir_filter(int input[N], int output[N], int coeffs[TAPS]) {
    #pragma HLS ARRAY_PARTITION variable=coeffs type=cyclic dim=1 factor=4
    #pragma HLS PIPELINE II=2

    int i, j;
    for (i = 0; i < N; i++) {
        #pragma HLS UNROLL factor=8
        int acc = 0;
        for (j = 0; j < TAPS; j++) {
            #pragma HLS UNROLL factor=4
            int idx = i - j;
            if (idx >= 0)
                acc += input[idx] * coeffs[j];
        }
        output[i] = acc;
    }
}
