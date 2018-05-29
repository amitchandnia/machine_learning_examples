# https://deeplearningcourses.com/c/data-science-natural-language-processing-in-python
# https://www.udemy.com/data-science-natural-language-processing-in-python

# Author: http://lazyprogrammer.me
from __future__ import print_function, division
from future.utils import iteritems
from builtins import range
# Note: you may need to update your version of future
# sudo pip install -U future

import os, sys
import string
import numpy as np
import matplotlib.pyplot as plt
from scipy.sparse import lil_matrix, csr_matrix, save_npz, load_npz
from scipy.spatial.distance import cosine as cos_dist
from sklearn.metrics.pairwise import pairwise_distances
from glob import glob


# input files
files = glob('../large_files/enwiki*.txt')


# unfortunately these work different ways
def remove_punctuation_2(s):
    return s.translate(None, string.punctuation)

def remove_punctuation_3(s):
    return s.translate(str.maketrans('','',string.punctuation))

if sys.version.startswith('2'):
    remove_punctuation = remove_punctuation_2
else:
    remove_punctuation = remove_punctuation_3


# max vocab size
V = 2000

# context size
context_size = 10

# word counts
all_word_counts = {}

# get the top V words
num_lines = 0
num_tokens = 0
for f in files:
  for line in open(f):
    # don't count headers, structured data, lists, etc...
    if line and line[0] not in ('[', '*', '-', '|', '=', '{', '}'):
      num_lines += 1
      for word in remove_punctuation(line).lower().split():
        num_tokens += 1
        if word not in all_word_counts:
          all_word_counts[word] = 0
        all_word_counts[word] += 1
print("num_lines:", num_lines)
print("num_tokens:", num_tokens)


# words I really want to keep
keep_words = [
  'king', 'man', 'queen', 'woman',
  'heir', 'heiress', 'prince', 'princess',
  'nephew', 'niece', 'uncle', 'aunt',
  'husband', 'wife', 'brother', 'sister',
  'tokyo', 'beijing',  'dallas', 'texas',
  'january', 'february', 'march',
  'april', 'may', 'june',
  'july', 'august', 'september',
  'october', 'november', 'december',
  'actor', 'actress',
  'rice', 'bread', 'miami', 'florida',
  'walk', 'walking', 'swim', 'swimming',
]
for w in keep_words:
  all_word_counts[w] = float('inf')


# sort in descending order
all_word_counts = sorted(all_word_counts.items(), key=lambda x: x[1], reverse=True)

# keep just the top V words
# save a slot for <UNK>
V = min(V, len(all_word_counts))
top_words = [w for w, count in all_word_counts[:V-1]] + ['<UNK>']
# TODO: try it without UNK at all

# reverse the array to get word2idx mapping
word2idx = {w:i for i, w in enumerate(top_words)}
unk = word2idx['<UNK>']

# for w in ('king', 'man', 'queen', 'woman', 'france', 'paris', \
#   'london', 'england', 'italy', 'rome', \
#   'france', 'french', 'english', 'england', \
#   'japan', 'japanese', 'chinese', 'china', \
#   'italian', 'australia', 'australian' \
#   'japan', 'tokyo', 'china', 'beijing'):
#   assert(w in word2idx)


if not os.path.exists('pmi_counts_%s.npz' % V):
  # init counts
  wc_counts = lil_matrix((V, V))

  ### make PMI matrix
  # add counts
  k = 0
  # for line in open('../large_files/text8'):
  for f in files:
    for line in open(f):
      # don't count headers, structured data, lists, etc...
      if line and line[0] not in ('[', '*', '-', '|', '=', '{', '}'):
        line_as_idx = []
        for word in remove_punctuation(line).lower().split():
          if word in word2idx:
            idx = word2idx[word]
            # line_as_idx.append(idx)
          else:
            idx = unk
            # pass
          line_as_idx.append(idx)

        for i, w in enumerate(line_as_idx):
          # keep count
          k += 1
          if k % 10000 == 0:
            print("%s/%s" % (k, num_tokens))

          start = max(0, i - context_size)
          end   = min(len(line_as_idx), i + context_size)
          for c in line_as_idx[start:end]:
            wc_counts[w, c] += 1
  print("Finished counting")

  save_npz('pmi_counts_%s.npz' % V, csr_matrix(wc_counts))

else:
  wc_counts = load_npz('pmi_counts_%s.npz' % V)


# context counts get raised ^ 0.75
c_counts = wc_counts.sum(axis=0).A.flatten() ** 0.75
c_probs = c_counts / c_counts.sum()
c_probs = c_probs.reshape(1, V)


# PMI(w, c) = #(w, c) / #(w) / p(c)
pmi = wc_counts / wc_counts.sum(axis=1) / c_probs
print("type(pmi):", type(pmi))
logX = np.log(pmi.A + 1) #+ np.log(100)
print("type(logX):", type(logX))
logX[logX < 0] = 0


### do alternating least squares


# latent dimension
D = 50
reg = 0.


# initialize weights
W = np.random.randn(V, D) / np.sqrt(V + D)
b = np.zeros(V)
U = np.random.randn(V, D) / np.sqrt(V + D)
c = np.zeros(V)
mu = logX.mean()


costs = []
for epoch in range(10):
  print("epoch:", epoch)
  delta = W.dot(U.T) + b.reshape(V, 1) + c.reshape(1, V) + mu - logX
  cost = ( delta * delta ).sum()
  costs.append(cost)

  # update W
  for i in range(V):
    matrix = reg*np.eye(D) + U.T.dot(U)
    vector = (logX[i,:] - b[i] - c - mu).dot(U)
    W[i] = np.linalg.solve(matrix, vector)

  # update b
  for i in range(V):
    numerator = (logX[i,:] - W[i].dot(U.T) - c - mu).sum()
    b[i] = numerator / V #/ (1 + reg)

  # update U
  for j in range(V):
    matrix = reg*np.eye(D) + W.T.dot(W)
    vector = (logX[:,j] - b - c[j] - mu).dot(W)
    U[j] = np.linalg.solve(matrix, vector)

  # update c
  for j in range(V):
    numerator = (logX[:,j] - W.dot(U[j]) - b  - mu).sum()
    c[j] = numerator / V #/ (1 + reg)

plt.plot(costs)
plt.show()




### test it
king  = W[word2idx['king']]
man   = W[word2idx['man']]
queen = W[word2idx['queen']]
woman = W[word2idx['woman']]

vec = king - man + woman

# find closest
# closest = None
# min_dist = float('inf')
# for i in range(len(W)):
#   dist = cos_dist(W[i], vec)
#   if dist < min_dist:
#     closest = i
#     min_dist = dist

# set word embedding matrix
# W = (W + U) / 2

distances = pairwise_distances(vec.reshape(1, D), W, metric='cosine').reshape(V)
idx = distances.argsort()[:10]

print("closest 10:")
for i in idx:
  print(top_words[i], distances[i])

print("dist to queen:", cos_dist(W[word2idx['queen']], vec))



def analogy(pos1, neg1, pos2, neg2):
  # don't actually use pos2 in calculation, just print what's expected
  print("testing: %s - %s = %s - %s" % (pos1, neg1, pos2, neg2))
  for w in (pos1, neg1, pos2, neg2):
    if w not in word2idx:
      print("Sorry, %s not in word2idx" % w)
      return

  p1 = W[word2idx[pos1]]
  n1 = W[word2idx[neg1]]
  p2 = W[word2idx[pos2]]
  n2 = W[word2idx[neg2]]

  vec = p1 - n1 + n2

  distances = pairwise_distances(vec.reshape(1, D), W, metric='cosine').reshape(V)
  idx = distances.argsort()[:10]

  # pick the best that's not p1, n1, or n2
  best_idx = -1
  keep_out = [word2idx[w] for w in (pos1, neg1, neg2)]
  for i in idx:
    if i not in keep_out:
      best_idx = i
      break

  print("got: %s - %s = %s - %s" % (pos1, neg1, top_words[best_idx], neg2))
  print("closest 10:")
  for i in idx:
    print(top_words[i], distances[i])

  print("dist to %s:" % pos2, cos_dist(p2, vec))


analogy('king', 'man', 'queen', 'woman')
analogy('miami', 'florida', 'dallas', 'texas')
# analogy('einstein', 'scientist', 'picasso', 'painter')
analogy('china', 'rice', 'england', 'bread')
analogy('man', 'woman', 'he', 'she')
analogy('man', 'woman', 'uncle', 'aunt')
analogy('man', 'woman', 'brother', 'sister')
analogy('man', 'woman', 'husband', 'wife')
analogy('man', 'woman', 'actor', 'actress')
analogy('man', 'woman', 'father', 'mother')
analogy('heir', 'heiress', 'prince', 'princess')
analogy('nephew', 'niece', 'uncle', 'aunt')
analogy('france', 'paris', 'japan', 'tokyo')
analogy('france', 'paris', 'china', 'beijing')
analogy('february', 'january', 'december', 'november')
analogy('france', 'paris', 'italy', 'rome')
analogy('paris', 'france', 'rome', 'italy')
analogy('france', 'french', 'england', 'english')
analogy('japan', 'japanese', 'china', 'chinese')
analogy('japan', 'japanese', 'italy', 'italian')
analogy('japan', 'japanese', 'australia', 'australian')
analogy('walk', 'walking', 'swim', 'swimming')
