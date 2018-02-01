from cntk.layers import *


def BiRecurrence(fwd, bwd):
    Sequential([
        (Recurrence(fwd),
         Recurrence(bwd, go_backwards=True)),
        splice
    ])

    # source=h  hidden=d_t-1
    @C.Function
    def attention(source, hidden, attention_dim):
        with default_options(bias=None):
            s = Dense(1, activation=tanh)(
                C.plus(
                    Dense(attention_dim),  # for d_t-1
                    Dense(attention_dim))  # for h_j
            )
            a = C.softmax(s)
