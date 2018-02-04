from cntk.layers import *

from script.utils import BiRecurrence

word_emb_dim = 300
feature_emb_dim = 50
hidden_dim = 150
attention_dim = 150
vocab_dim = 10000  # issue

question_seq_axis = C.Axis('questionAxis')
passage_seq_axis = C.Axis('passageAxis')
answer_seq_axis = C.Axis('answerAxis')
question_seq = C.sequence.input_variable((vocab_dim), sequence_axis=question_seq_axis, name='raw_input')
passage_seq = C.sequence.input_variable((vocab_dim), sequence_axis=passage_seq_axis, name='raw_input')
answer_seq = C.sequence.input_variable((vocab_dim), sequence_axis=answer_seq_axis, name='raw_input')


def question_encoder_factory():
    with default_options(initial_state=0.1):
        model = Sequential([
            Embedding(word_emb_dim, name='embed'),
            Stabilizer(),
            # ht = BiGRU(ht−1, etq)
            BiRecurrence(GRU(shape=hidden_dim), GRU(shape=hidden_dim)),
        ], name='question_encoder')
    return model


def passage_encoder_factory():
    with default_options(initial_state=0.1):
        model = Sequential([
            Embedding(word_emb_dim, name='embed'),
            Stabilizer(),
            # ht = BiGRU(ht−1, [etp, fts, fte])
            BiRecurrence(GRU(shape=hidden_dim), GRU(shape=hidden_dim))
        ], name='passage_encoder')
    return model


def decoder_initialization_factory():
    return Sequential([
        splice,
        Dense(hidden_dim, activation=C.tanh, bias=True)
    ])


question_encoder = question_encoder_factory()
passage_encoder = passage_encoder_factory()

q_attention_layer = AttentionModel(attention_dim)
p_attention_layer = AttentionModel(attention_dim)
emb_layer = Embedding(word_emb_dim)
decoder_gru = GRU(hidden_dim)
# question encoder hidden state
h_q = question_encoder(question_seq)
# passage encoder hidden state
h_p = passage_encoder(passage_seq)

h_q1 = C.sequence.last(h_q)
h_p1 = C.sequence.last(h_p)

# decoder_initialization
r = splice(C.slice(h_q1, 0, hidden_dim, 0), C.slice(h_q1, 0, hidden_dim, 0))
d_0 = Dense(hidden_dim*2, activation=C.tanh, bias=True)(r)

def output_layer(emb_word,att_p,att_q,hidden):
    emb_word_ph=C.placeholder()
    att_p_ph=C.placeholder()
    att_q_ph=C.placeholder()
    hidden_ph=C.placeholder()
    return

# d_0 = splice
# print(d_0.shape)
# answer_seq = C.sequence.delay(answer_seq)


# @C.Function
# def GRU__with_attention(hidden, x):
#     p_att = p_attention(h_p, hidden)
#     q_att = q_attention(h_q, hidden)
#     x = splice(x, p_att, q_att)
#     return gru(hidden, x)



def decoder(word_prev, hidden_prev, att_p_prev, att_q_prev):
    emb = emb_layer(word_prev)
    x = C.splice(word_prev, att_p_prev, att_q_prev)
    hidden = decoder_gru(hidden_prev, x)
    att_p = p_attention_layer(h_p, hidden)
    att_q = q_attention_layer(h_q, hidden)
    word=output_layer()

#
# UnfoldFrom(decoder)