# lowdim <master> <inputFile_X> <inputFile_y> <mode> <outputFile> <k>"
# 
# perform two stages of dimensionality reduction
# first reduce each time series using the specified method
# then do PCA
# return low-dimensional subspace, as well as raw time
# series projected into that space
# each row is (x,y,z,timeseries)
#

import sys
import os
from numpy import *
from scipy.linalg import *
from scipy.io import * 
from pyspark import SparkContext
import logging

argsIn = sys.argv[1:]

if len(argsIn) < 8:
  print >> sys.stderr, \
  "(lowdim) usage: lowdim <master> <inputFile_X> <inputFile_y> <outputFile> <analMode> <k> <inputMode> <outputMode> <startInd> <endInd> <shuf>"
  exit(-1)

def parseVector(line,mode="raw",xyz=0,inds=None):
	vec = [float(x) for x in line.split(' ')]
	ts = array(vec[3:]) # get tseries
	if inds is not None :
		ts = ts[inds[0]:inds[1]]
	if mode == "dff" :
		meanVal = mean(ts)
		ts = (ts - meanVal) / (meanVal + 0.1)
	if xyz == 1 :
		return ((int(vec[0]),int(vec[1]),int(vec[2])),ts)
	else :
		return ts

def clip(vec,val):
	vec[vec<val] = val
	return vec

def threshMap(x,y,eigs,rng1,rng2):
	vals = inner(dot(y,x) - mean(dot(y,x)),eigs)
	vals[0] = -vals[0]
	r = sqrt(vals[0]**2 + vals[1]**2)
	t = arctan2(vals[1], vals[0])
	out = zeros(shape(x))
	if (t > rng1) | (t < rng2):
		out = x * r
	return out

def getT(x,y,eigs):
	vals = inner(dot(y,x) - mean(dot(y,x)),eigs)
	t = arctan2(vals[1], vals[0])
	return t

def getR(x,y,eigs):
	vals = inner(dot(y,x) - mean(dot(y,x)),eigs)
	r = sqrt(vals[0]**2 + vals[1]**2)
	return r

def inRange(val,rng1,rng2):
	if (val > rng1) & (val < rng2):
		return True
	else:
		return False

def getTuningParams(valx,valy) :
	y = (valy - valy.min())/(valy.max() - valy.min())
	r = inner(y,exp(1j*valx))
	mu = angle(r)
	v = absolute(r)/sum(y)
	return (mu,v)

def getRegression(x,y) :
	resp = dot(y,x)[1:]
	inds1 = range(0,20)
	inds2 = range(20,40)
	resp = concatenate((resp[inds1] - mean(resp[inds1]),resp[inds2] - mean(resp[inds2])))
	return resp

def getTiming(r) : 
	x = arange(0,20)
	r = (r - min(r)) / (max(r) - min(r))
	r = r / sum(r)
	return dot(x,r)

# parse inputs
sc = SparkContext(argsIn[0], "lowdim")
inputFile_X = str(argsIn[1])
inputFile_y = str(argsIn[2])
outputFile = str(argsIn[3]) + "-lowdim"
analMode = str(argsIn[4])
k = int(argsIn[5])
inputMode = str(argsIn[6])
outputMode = str(argsIn[7])

if not os.path.exists(outputFile):
    os.makedirs(outputFile)
logging.basicConfig(filename=outputFile+'/'+'stdout.log',level=logging.INFO,format='%(asctime)s %(message)s',datefmt='%m/%d/%Y %I:%M:%S %p')

# parse data
logging.info("(lowdim) loading data")
y = loadmat(inputFile_y)['y']
y = y.astype(float)
lines_X = sc.textFile(inputFile_X) # the data

if len(argsIn) > 8 :
	logging.info("(lowdim) using specified indices")
	startInd = float(argsIn[8])
	endInd = float(argsIn[9])
	y = y[:,startInd:endInd]
	X = lines_X.map(lambda x : parseVector(x,"dff",0,(startInd,endInd))).cache()
else :
	X = lines_X.map(lambda x : parseVector(x,"dff")).cache()

if len(argsIn) > 10 :
	shufType = argsIn[10]
	if shufType == 'stimcirc' :
		for iy in range(0,y.shape[0]) :
			shift = int(round(random.rand(1)*y.shape[1]))
			y[iy,:] = roll(y[iy,:],shift)
	if shufType == 'stimrand':
		for iy in range(0,y.shape[0]) :
			random.shuffle(y[iy,:])
	if shufType == 'resprnd':
		X = X.map(lambda x : random.shuffle(x))
	if shufType == 'respcirc':
		n = len(X.first())
		X = X.map(lambda x : roll(x,int(round(random.rand(1)*n))))

if analMode == 'mean' :
	resp = X.map(lambda x : dot(y,x))
if analMode == 'corr' :
	resp = X.map(lambda x : dot(y,(x-mean(x))/norm(x)))
if analMode == 'regress' : 
	yhat = dot(inv(dot(y,transpose(y))),y)
	resp = X.map(lambda x : dot(yhat,x)[1:])
	r2 = X.map(lambda x : 1.0 - sum((dot(transpose(y),dot(yhat,x)) - x) ** 2) / sum((x - mean(x)) ** 2)).collect()
	savemat(outputFile+"/"+"r2.mat",mdict={'r2':r2},oned_as='column',do_compression='true')
	#vals = array([0,2,4,6,8,10,12,14,16,20,25,30])
	#vals = array([2.5,7.5,12.5,17.5,22.5,27.5,32.5,37.5,42.5,47.5])
	vals = range(0,360,360/12)
	tuning = resp.map(lambda x : clip(x,0)).map(lambda x : x / sum(x)).map(lambda x : dot(x,vals)).collect()
	savemat(outputFile+"/"+"tuning.mat",mdict={'tuning':tuning},oned_as='column',do_compression='true')
if analMode == 'regress2' : 
	yhat = dot(inv(dot(y,transpose(y))),y)
	resp = X.map(lambda x : getRegression(x,yhat))
	r = resp.map(lambda r : norm(r)).collect()
	p1 = resp.map(lambda r : norm(r[0:20])).collect()
	p2 = resp.map(lambda r : norm(r[20:40])).collect()
	p3 = resp.map(lambda r : getTiming(r[20:40])).collect()
	savemat(outputFile+"/"+"r.mat",mdict={'r':r},oned_as='column',do_compression='true')
	savemat(outputFile+"/"+"p1.mat",mdict={'p1':p1},oned_as='column',do_compression='true')
	savemat(outputFile+"/"+"p2.mat",mdict={'p2':p2},oned_as='column',do_compression='true')
	savemat(outputFile+"/"+"p3.mat",mdict={'p3':p3},oned_as='column',do_compression='true')


# compute covariance
logging.info("(lowdim) getting count")
n = resp.count()
logging.info("(lowdim) computing covariance")
cov = resp.map(lambda x : outer(x-mean(x),x-mean(x))).reduce(lambda x,y : (x + y)) / n

logging.info("(lowdim) doing eigendecomposition")
w, v = eig(cov)
w = real(w)
v = real(v)
inds = argsort(w)[::-1]
sortedDim2 = transpose(v[:,inds[0:k]])
latent = w[inds[0:k]]

logging.info("(lowdim) writing evecs and evals")
savemat(outputFile+"/"+"cov.mat",mdict={'cov':cov},oned_as='column',do_compression='true')
savemat(outputFile+"/"+"evecs.mat",mdict={'evecs':sortedDim2},oned_as='column',do_compression='true')
savemat(outputFile+"/"+"evals.mat",mdict={'evals':latent},oned_as='column',do_compression='true')


if outputMode == 'traj':
	#traj = zeros((k,len(X.first())))
	#for ik in range(0,k):
	logging.info("(lowdim) writing trajectories")
	traj = X.map(lambda x : outer(x,inner(dot(y,x) - mean(dot(y,x)),sortedDim2))).reduce(lambda x,y : x + y)
	savemat(outputFile+"/"+"traj.mat",mdict={'traj':traj},oned_as='column',do_compression='true')

if outputMode == 'maps':
	for ik in range(0,k):
		logging.info("(lowdim) writing scores for pc " + str(ik))
		#out = X.map(lambda x : float16(inner(dot(y,x) - mean(dot(y,x)),sortedDim2[ik,:])))
		#out = resp.map(lambda x : float16(inner(x - mean(x),sortedDim2[ik,:])))
		out = X.map(lambda x : float16(inner(getRegression(x,yhat),sortedDim2[ik,:])))
		savemat(outputFile+"/"+"scores-"+str(ik)+".mat",mdict={'scores':out.collect()},oned_as='column',do_compression='true')

if outputMode == 'tuning':
	xvals = arange(0,2*pi,2*pi/12)
	r = resp.map(lambda x : float16(sqrt(sum(inner(x-mean(x),sortedDim2) ** 2))))
	savemat(outputFile+"/"+"r.mat",mdict={'r':r.collect()},oned_as='column',do_compression='true')
	p = resp.map(lambda x : float16(getTuningParams(xvals,dot(inner(x-mean(x),sortedDim2),sortedDim2))))
	savemat(outputFile+"/"+"tuning-param.mat",mdict={'p':p.collect()},oned_as='column',do_compression='true')

if outputMode == 'pie':
	nT = 10
	ts = linspace(-pi,pi,nT)
	traj = zeros((nT-1,len(X.first())))
	for it in  range(0,nT-1):
		subset = X.filter(lambda x : inRange(getT(x,y,sortedDim2),ts[it],ts[it+1]))
		traj[it,:] = subset.map(lambda x : x * getR(x,y,sortedDim2)).reduce(lambda x,y : x + y) / subset.count()
	savemat(outputFile+"/"+"traj.mat",mdict={'traj':traj},oned_as='column',do_compression='true')

# r = X.map(lambda x : getR(x,y,sortedDim2)).collect()
# savemat(outputFile+"/"+"r"+".mat",mdict={'r':r},oned_as='column',do_compression='true')

# t = X.map(lambda x : getT(x,y,sortedDim2)).collect()
# savemat(outputFile+"/"+"t"+".mat",mdict={'t':t},oned_as='column',do_compression='true')


# 




