import importlib
import os
import pickle

from cntk.layers import *

from utils import BiRNN


class AnswerSynthesisModel(object):
    def __init__(self, config_file):
        config = importlib.import_module(config_file)
        data_config = config.data_config
        model_config = config.answer_synthesis_model

        self.abs_path = os.path.dirname(os.path.abspath(__file__))
        pickle_file = os.path.join(self.abs_path, 'data', data_config['pickle_file'])
        with open(pickle_file, 'rb') as vf:
            known, vocab, chars, npglove_matrix = pickle.load(vf)

        # self.npglove_matrix = npglove_matrix
        self.emb_dim = model_config['emb_dim']
        self.hidden_dim = model_config['hidden_dim']
        self.attention_dim = model_config['attention_dim']
        self.dropout_rate = model_config['dropout']
        self.vocab_dim = len(vocab)
        self.question_seq_axis = C.Axis.new_unique_dynamic_axis('questionAxis')
        self.passage_seq_axis = C.Axis.new_unique_dynamic_axis('passageAxis')
        self.answer_seq_axis = C.Axis.new_unique_dynamic_axis('answerAxis')
        self.PassageSequence = SequenceOver[self.passage_seq_axis][Tensor[self.vocab_dim]]
        self.QuestionSequence = SequenceOver[self.question_seq_axis][Tensor[self.vocab_dim]]
        self.AnswerSequence = SequenceOver[self.answer_seq_axis][Tensor[self.vocab_dim]]
        self.emb_layer = Embedding(self.emb_dim, init=npglove_matrix)
        # self.bos = '<BOS>'
        # self.eos = '<EOS>'
        # # todo: what about parameter?
        #
        # self.start_word = C.constant(np.zeros(self.vocab_dim, dtype=np.float32))
        # self.end_word_idx = vocab[self.eos]

    def question_encoder_factory(self):
        with default_options(enable_self_stabilization=True):
            model = Sequential([
                self.emb_layer,
                Stabilizer(),
                # ht = BiGRU(ht−1, etq)
                BiRNN(GRU(shape=self.hidden_dim), GRU(shape=self.hidden_dim)),
                Dropout(self.dropout_rate)
            ], name='question_encoder')
        return model

    def passage_encoder_factory(self):
        with default_options(enable_self_stabilization=True):
            model = Sequential([
                self.emb_layer,
                Stabilizer(),
                # ht = BiGRU(ht−1, [etp, fts, fte])
                BiRNN(GRU(shape=self.hidden_dim), GRU(shape=self.hidden_dim)),
                Dropout(self.dropout_rate)
            ], name='passage_encoder')
        return model

    def model_factory(self):
        question_encoder = self.question_encoder_factory()
        passage_encoder = self.passage_encoder_factory()
        # todo: add bias by self
        q_attention_layer = AttentionModel(self.attention_dim, name='query_attention')
        p_attention_layer = AttentionModel(self.attention_dim, name='passage_attention')
        emb_layer = self.emb_layer
        decoder_gru = GRU(self.hidden_dim, enable_self_stabilization=True)
        # decoder_init_dense_p = Dense(self.hidden_dim//2, activation=C.tanh, bias=True)
        # decoder_init_dense_q = Dense(self.hidden_dim//2, activation=C.tanh, bias=True)
        decoder_init_dense = Dense(self.hidden_dim, activation=C.tanh, bias=True)
        # for readout_layer
        emb_dense = Dense(self.vocab_dim)
        att_p_dense = Dense(self.vocab_dim)
        att_q_dense = Dense(self.vocab_dim)
        hidden_dense = Dense(self.vocab_dim)
        # todo: is random better? is parameter better?
        att_p_0 = C.constant(np.zeros(self.attention_dim, dtype=np.float32))
        att_q_0 = C.constant(np.zeros(self.attention_dim, dtype=np.float32))

        @C.Function
        def decoder(question: self.QuestionSequence, passage: self.PassageSequence, word_prev: self.AnswerSequence):
            # question encoder hidden state
            h_q = question_encoder(question)
            # passage encoder hidden state
            h_p = passage_encoder(passage)
            # print(h_p)
            # print(h_p.output)
            # print(type(h_p))
            # print(type(h_p.output))
            # print('=================')

            h_q1 = C.sequence.last(h_q)
            h_p1 = C.sequence.last(h_p)

            emb_prev = emb_layer(word_prev)
            @C.Function
            def gru_with_attention(hidden_prev, att_p_prev, att_q_prev, emb_prev):
                x = C.splice(emb_prev, att_p_prev, att_q_prev, axis=0)
                hidden = C.dropout(decoder_gru(hidden_prev, x), self.dropout_rate)
                att_p = C.dropout(p_attention_layer(h_p.output, hidden), self.dropout_rate)
                att_q = C.dropout(q_attention_layer(h_q.output, hidden), self.dropout_rate)
                return (hidden, att_p, att_q)

            # print(gru_with_attention)

            # decoder_initialization
            d_0 = (splice(C.slice(h_p1, 0, self.hidden_dim, 0),
                          C.slice(h_q1, 0, self.hidden_dim, 0)) >> decoder_init_dense).output
            # todo: use weight sum
            # d_0=C.splice(decoder_init_dense_p(h_p1),decoder_init_dense_q(h_q1))
            # print(d_0)
            # print(d_0.output)

            init_state = (d_0, att_p_0, att_q_0)
            rnn = Recurrence(gru_with_attention, initial_state=init_state, return_full_state=True)(emb_prev)
            # todo: big issues here??
            hidden, att_p, att_q = rnn[0], rnn[1], rnn[2]
            readout = C.plus(
                emb_dense(emb_prev),
                att_q_dense(att_q),
                att_p_dense(att_p),
                hidden_dense(hidden)
            )
            word = C.sequence.softmax(readout)
            return word

        return decoder

    def model_train_factory(self, s2smodel):
        @C.Function
        def model_train(question: self.QuestionSequence, passage: self.PassageSequence, answer: self.AnswerSequence):
            past_answer = Delay(initial_state=0)(answer)
            return s2smodel(question, passage, past_answer)

        return model_train

    # def model_greedy_factory(self):
    #     s2smodel = self.model_factory()
    #
    #     # todo: use beam search
    #     @C.Function
    #     def model_greedy(question: self.QuestionSequence, passage: self.PassageSequence):
    #         unfold = C.layers.UnfoldFrom(lambda answer: s2smodel(question, passage, answer),
    #                                      until_predicate=lambda w: w[..., self.end_word_idx]
    #                                      )
    #         return unfold(initial_state=self.start_word, dynamic_axes_like=passage)  # todo: use a new infinity axis
    #
    #     return model_greedy

    def criterion_factory(self):
        @C.Function
        def criterion(answer, answer_label):
            loss = C.cross_entropy_with_softmax(answer, answer_label)
            errs = C.minus(1, C.classification_error(answer, answer_label))  # todo: runtime rouge-L
            return (loss, errs)

        return criterion

    def model(self):
        question_seq = C.sequence.input_variable(self.vocab_dim, sequence_axis=self.question_seq_axis, name='question')
        passage_seq = C.sequence.input_variable(self.vocab_dim, sequence_axis=self.passage_seq_axis, name='passage')
        answer_seq = C.sequence.input_variable(self.vocab_dim, sequence_axis=self.answer_seq_axis, name='answer')

        s2smodel = self.model_factory()

        train_model = self.model_train_factory(s2smodel)
        # print(train_model)
        criterion_model = self.criterion_factory()

        synthesis_answer = train_model(question_seq, passage_seq, answer_seq)
        criterion = criterion_model(synthesis_answer, answer_seq)

        return synthesis_answer, criterion


a = AnswerSynthesisModel('config')
a.model()
